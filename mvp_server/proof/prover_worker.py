from __future__ import annotations

import argparse
import time

from mvp_server.config import AppConfig

from .proof_job_manifest import ProofJobManifest
from .proof_store import ProofStore
from .zklora_adapter import ZkLoraAdapter


class ProverWorker:
    """Manifest-driven worker that consumes queued proof jobs in a separate process."""

    def __init__(
        self,
        manifest: ProofJobManifest,
        proof_store: ProofStore,
        adapter: ZkLoraAdapter,
    ) -> None:
        self.manifest = manifest
        self.proof_store = proof_store
        self.adapter = adapter

    def run_once(self) -> bool:
        job = self.manifest.claim_next()
        if job is None:
            return False

        request_id = job["request_id"]
        module_id = job["module_id"]
        pending_at = time.time()
        self.proof_store.set_status(
            request_id,
            "pending",
            module_id=module_id,
            event_at=pending_at,
            lifecycle_key="worker_claimed_at",
        )
        try:
            result = self.adapter.prove(job)
            self.proof_store.set_terminal(
                request_id=request_id,
                status="ready",
                module_id=module_id,
                artifact_refs={
                    "proof": result.proof_ref,
                    "public": result.public_ref,
                    "prover_duration_ms": f"{result.duration_ms:.3f}",
                },
                event_at=time.time(),
                lifecycle_key="proof_ready_at",
            )
        except Exception as exc:
            self.proof_store.set_terminal(
                request_id=request_id,
                status="failed",
                module_id=module_id,
                error_code="prove_failed",
                error_message=str(exc),
                event_at=time.time(),
                lifecycle_key="proof_failed_at",
            )
        return True


def build_worker_from_config(config: AppConfig) -> ProverWorker:
    manifest = ProofJobManifest(
        path=config.resolved_proof_manifest_path(),
        claims_path=config.resolved_proof_claims_path(),
    )
    proof_store = ProofStore(path=config.resolved_proof_store_path())
    adapter = ZkLoraAdapter(artifacts_root=config.artifacts_root)
    return ProverWorker(manifest=manifest, proof_store=proof_store, adapter=adapter)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-2 proof worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job")
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=0,
        help="Stop after processing N jobs (0 means unlimited)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config = AppConfig.from_env()
    worker = build_worker_from_config(config)

    processed = 0
    while True:
        did_work = worker.run_once()
        if did_work:
            processed += 1
        if args.once:
            return 0
        if args.max_jobs > 0 and processed >= args.max_jobs:
            return 0
        if not did_work:
            time.sleep(config.worker_poll_interval_ms / 1000.0)


if __name__ == "__main__":
    raise SystemExit(main())
