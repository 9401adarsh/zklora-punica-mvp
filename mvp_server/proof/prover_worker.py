from __future__ import annotations

import argparse
import queue
import threading
import time
from typing import Any, Callable

from mvp_server.config import AppConfig

from .proof_job_manifest import ProofJobManifest
from .proof_store import ProofStore
from .zklora_adapter import ZkLoraAdapter

AdapterFactory = Callable[[], Any]


class ProverWorker:
    """Manifest-driven proof worker with optional threaded processing."""

    def __init__(
        self,
        manifest: ProofJobManifest,
        proof_store: ProofStore,
        adapter: Any | None = None,
        adapter_factory: AdapterFactory | None = None,
        proof_worker_threads: int = 1,
    ) -> None:
        if adapter is None and adapter_factory is None:
            raise ValueError("either adapter or adapter_factory must be provided")
        self.manifest = manifest
        self.proof_store = proof_store
        self._adapter = adapter
        self._adapter_factory = adapter_factory
        self.proof_worker_threads = max(1, int(proof_worker_threads))

    def _get_or_create_single_adapter(self) -> Any:
        if self._adapter is not None:
            return self._adapter
        if self._adapter_factory is None:
            raise RuntimeError("adapter_factory is not configured")
        self._adapter = self._adapter_factory()
        return self._adapter

    @staticmethod
    def _job_field(job: Any, key: str) -> str:
        if isinstance(job, dict):
            return str(job[key])
        return str(getattr(job, key))

    def _claim_and_mark_pending(self) -> dict[str, Any] | None:
        job = self.manifest.claim_next()
        if job is None:
            return None

        request_id = self._job_field(job, "request_id")
        module_id = self._job_field(job, "module_id")
        pending_at = time.time()
        self.proof_store.set_status(
            request_id,
            "pending",
            module_id=module_id,
            event_at=pending_at,
            lifecycle_key="worker_claimed_at",
        )
        return job

    def _process_claimed_job(self, job: dict[str, Any], adapter: Any) -> None:
        request_id = self._job_field(job, "request_id")
        module_id = self._job_field(job, "module_id")

        try:
            result = adapter.prove(job)
            artifact_refs = {
                "proof": result.proof_ref,
                "public": result.public_ref,
                "prover_duration_ms": f"{result.duration_ms:.3f}",
            }
            if result.stage_setup_s is not None:
                artifact_refs["stage_setup_s"] = f"{result.stage_setup_s:.6f}"
            if result.stage_witness_s is not None:
                artifact_refs["stage_witness_s"] = f"{result.stage_witness_s:.6f}"
            if result.stage_prove_s is not None:
                artifact_refs["stage_prove_s"] = f"{result.stage_prove_s:.6f}"
            if result.stage_total_s is not None:
                artifact_refs["stage_total_s"] = f"{result.stage_total_s:.6f}"
            if result.setup_cache_enabled is not None:
                artifact_refs["setup_cache_enabled"] = "1" if result.setup_cache_enabled else "0"
            if result.setup_cache_hit is not None:
                artifact_refs["setup_cache_hit"] = "1" if result.setup_cache_hit else "0"
            if result.setup_cache_key is not None:
                artifact_refs["setup_cache_key"] = result.setup_cache_key
            self.proof_store.set_terminal(
                request_id=request_id,
                status="ready",
                module_id=module_id,
                artifact_refs=artifact_refs,
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

    def run_once(self) -> bool:
        job = self._claim_and_mark_pending()
        if job is None:
            return False
        adapter = self._get_or_create_single_adapter()
        self._process_claimed_job(job, adapter)
        return True

    def run(self, max_jobs: int = 0, poll_interval_s: float = 0.25) -> int:
        if max_jobs < 0:
            raise ValueError("max_jobs must be >= 0")

        work_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(
            maxsize=self.proof_worker_threads * 4
        )
        processed = 0
        processed_lock = threading.Lock()

        def worker_loop(adapter: Any) -> None:
            nonlocal processed
            while True:
                job = work_queue.get()
                try:
                    if job is None:
                        return
                    self._process_claimed_job(job, adapter)
                    with processed_lock:
                        processed += 1
                finally:
                    work_queue.task_done()

        workers: list[threading.Thread] = []
        for index in range(self.proof_worker_threads):
            if index == 0:
                adapter = self._get_or_create_single_adapter()
            elif self._adapter_factory is None:
                adapter = self._get_or_create_single_adapter()
            else:
                adapter = self._adapter_factory()
            thread = threading.Thread(target=worker_loop, args=(adapter,), daemon=True)
            workers.append(thread)
            thread.start()

        claimed = 0
        try:
            while True:
                if max_jobs > 0 and claimed >= max_jobs:
                    break

                job = self._claim_and_mark_pending()
                if job is None:
                    time.sleep(poll_interval_s)
                    continue

                claimed += 1
                work_queue.put(job)
        finally:
            for _ in workers:
                work_queue.put(None)
            work_queue.join()
            for thread in workers:
                thread.join(timeout=1.0)

        return processed


def build_worker_from_config(config: AppConfig) -> ProverWorker:
    manifest = ProofJobManifest(
        path=config.resolved_proof_manifest_path(),
        claims_path=config.resolved_proof_claims_path(),
    )
    proof_store = ProofStore(path=config.resolved_proof_store_path())

    def adapter_factory() -> ZkLoraAdapter:
        return ZkLoraAdapter(
            artifacts_root=config.artifacts_root,
            base_model_id=config.base_model_id,
            adapter_id=config.adapter_id,
            prover_backend=config.prover_backend,
        )

    return ProverWorker(
        manifest=manifest,
        proof_store=proof_store,
        adapter_factory=adapter_factory,
        proof_worker_threads=config.proof_worker_threads,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-4 proof worker")
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

    if args.once:
        worker.run_once()
        return 0

    try:
        worker.run(
            max_jobs=args.max_jobs,
            poll_interval_s=config.worker_poll_interval_ms / 1000.0,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
