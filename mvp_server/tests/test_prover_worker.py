from mvp_server.proof.proof_job_manifest import ProofJobManifest
from mvp_server.proof.proof_store import ProofStore
from mvp_server.proof.prover_worker import ProverWorker
from mvp_server.proof.zklora_adapter import ProveResult


class SuccessAdapter:
    def prove(self, _job):
        return ProveResult(
            proof_ref="/tmp/proof.pf",
            public_ref="/tmp/proof_settings.json",
            duration_ms=1.23,
        )


class FailingAdapter:
    def prove(self, _job):
        raise RuntimeError("prove: backend failure")


def test_prover_worker_pending_to_ready(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()

    manifest.append(
        {
            "request_id": "r1",
            "module_id": "m1",
            "witness_ref": str(tmp_path / "w1.json"),
        }
    )
    store.set_status("r1", "queued", module_id="m1")

    worker = ProverWorker(manifest=manifest, proof_store=store, adapter=SuccessAdapter())
    assert worker.run_once()

    record = store.get("r1")
    assert record is not None
    assert record.status == "ready"
    assert record.artifact_refs["proof"].endswith(".pf")
    assert record.artifact_refs["public"].endswith("_settings.json")


def test_prover_worker_pending_to_failed(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()

    manifest.append(
        {
            "request_id": "r2",
            "module_id": "m1",
            "witness_ref": str(tmp_path / "w2.json"),
        }
    )
    store.set_status("r2", "queued", module_id="m1")

    worker = ProverWorker(manifest=manifest, proof_store=store, adapter=FailingAdapter())
    assert worker.run_once()

    record = store.get("r2")
    assert record is not None
    assert record.status == "failed"
    assert record.error_code == "prove_failed"
    assert record.error_message
