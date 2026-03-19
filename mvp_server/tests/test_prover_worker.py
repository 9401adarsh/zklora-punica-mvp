from mvp_server.proof.proof_job_manifest import ProofJobManifest
from mvp_server.proof.proof_store import ProofStore
from mvp_server.proof.prover_worker import ProverWorker
from mvp_server.proof.zklora_adapter import ZkLoraAdapter


def test_prover_worker_pending_to_ready(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()
    adapter = ZkLoraAdapter(str(tmp_path))

    manifest.append(
        {
            "request_id": "r1",
            "module_id": "m1",
            "witness_ref": "/tmp/w1.json",
        }
    )
    store.set_status("r1", "queued", module_id="m1")

    worker = ProverWorker(manifest=manifest, proof_store=store, adapter=adapter)
    assert worker.run_once()

    record = store.get("r1")
    assert record is not None
    assert record.status == "ready"
    assert "proof" in record.artifact_refs


def test_prover_worker_pending_to_failed(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()
    adapter = ZkLoraAdapter(str(tmp_path))

    manifest.append(
        {
            "request_id": "r2",
            "module_id": "m1",
            "witness_ref": "/tmp/w2.json",
            "force_fail": True,
        }
    )
    store.set_status("r2", "queued", module_id="m1")

    worker = ProverWorker(manifest=manifest, proof_store=store, adapter=adapter)
    assert worker.run_once()

    record = store.get("r2")
    assert record is not None
    assert record.status == "failed"
    assert record.error_code == "prove_failed"
