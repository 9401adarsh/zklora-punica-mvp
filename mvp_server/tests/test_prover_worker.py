import json
import threading
import time

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
            stage_setup_s=0.01,
            stage_witness_s=0.02,
            stage_prove_s=0.03,
            stage_total_s=0.06,
        )


class FailingAdapter:
    def prove(self, _job):
        raise RuntimeError("prove: backend failure")


class PanicLikeError(BaseException):
    pass


class PanicLikeAdapter:
    def prove(self, _job):
        raise PanicLikeError("icicle panic")


class PatternAdapter:
    def __init__(self, fail_request_ids: set[str]) -> None:
        self._fail_request_ids = fail_request_ids

    def prove(self, job):
        request_id = str(job["request_id"])
        if request_id in self._fail_request_ids:
            raise RuntimeError(f"prove: backend failure ({request_id})")
        return ProveResult(
            proof_ref=f"/tmp/{request_id}.pf",
            public_ref=f"/tmp/{request_id}_settings.json",
            duration_ms=1.23,
        )


def _append_jobs(
    manifest: ProofJobManifest,
    store: ProofStore,
    tmp_path,
    count: int,
) -> list[str]:
    request_ids: list[str] = []
    for idx in range(count):
        request_id = f"r{idx}"
        request_ids.append(request_id)
        manifest.append(
            {
                "request_id": request_id,
                "module_id": "m1",
                "witness_ref": str(tmp_path / f"{request_id}.json"),
            }
        )
        store.set_status(request_id, "queued", module_id="m1")
    return request_ids


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
    assert float(record.artifact_refs["stage_setup_s"]) == 0.01
    assert float(record.artifact_refs["stage_witness_s"]) == 0.02
    assert float(record.artifact_refs["stage_prove_s"]) == 0.03
    assert float(record.artifact_refs["stage_total_s"]) == 0.06


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


def test_prover_worker_pending_to_failed_on_base_exception(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()

    manifest.append(
        {
            "request_id": "r_panic",
            "module_id": "m1",
            "witness_ref": str(tmp_path / "w_panic.json"),
        }
    )
    store.set_status("r_panic", "queued", module_id="m1")

    worker = ProverWorker(manifest=manifest, proof_store=store, adapter=PanicLikeAdapter())
    assert worker.run_once()

    record = store.get("r_panic")
    assert record is not None
    assert record.status == "failed"
    assert record.error_code == "prove_failed"
    assert "PanicLikeError" in (record.error_message or "")


def test_threaded_worker_base_exception_does_not_hang(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()

    manifest.append(
        {
            "request_id": "r_thread_panic",
            "module_id": "m1",
            "witness_ref": str(tmp_path / "w_thread_panic.json"),
        }
    )
    store.set_status("r_thread_panic", "queued", module_id="m1")

    worker = ProverWorker(
        manifest=manifest,
        proof_store=store,
        adapter_factory=lambda: PanicLikeAdapter(),
        proof_worker_threads=1,
    )
    started = time.time()
    processed = worker.run(max_jobs=1, poll_interval_s=0.001)
    elapsed = time.time() - started

    record = store.get("r_thread_panic")
    assert record is not None
    assert record.status == "failed"
    assert record.error_code == "prove_failed"
    assert elapsed < 2.0
    assert processed in {0, 1}


def test_threaded_worker_processes_all_jobs_no_duplicates(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()

    total_jobs = 24
    request_ids = _append_jobs(manifest, store, tmp_path=tmp_path, count=total_jobs)

    create_count = 0
    create_lock = threading.Lock()

    def adapter_factory() -> SuccessAdapter:
        nonlocal create_count
        with create_lock:
            create_count += 1
        return SuccessAdapter()

    worker = ProverWorker(
        manifest=manifest,
        proof_store=store,
        adapter_factory=adapter_factory,
        proof_worker_threads=2,
    )
    processed = worker.run(max_jobs=total_jobs, poll_interval_s=0.001)
    assert processed == total_jobs
    assert create_count == 2

    records = store.all_records()
    assert len(records) == total_jobs
    for request_id in request_ids:
        record = records[request_id]
        assert record.status == "ready"
        assert "worker_claimed_at" in record.lifecycle_timestamps
        assert "terminal_at" in record.lifecycle_timestamps

    claim_rows = [
        json.loads(line)
        for line in manifest.claims_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(claim_rows) == total_jobs
    assert len({row["request_id"] for row in claim_rows}) == total_jobs


def test_threaded_worker_failure_mapping_preserved(tmp_path) -> None:
    manifest = ProofJobManifest(
        str(tmp_path / "proof_jobs.jsonl"),
        claims_path=str(tmp_path / "proof_claims.jsonl"),
    )
    store = ProofStore()

    total_jobs = 12
    request_ids = _append_jobs(manifest, store, tmp_path=tmp_path, count=total_jobs)
    fail_ids = {request_id for idx, request_id in enumerate(request_ids) if idx % 3 == 0}

    worker = ProverWorker(
        manifest=manifest,
        proof_store=store,
        adapter_factory=lambda: PatternAdapter(fail_ids),
        proof_worker_threads=2,
    )
    processed = worker.run(max_jobs=total_jobs, poll_interval_s=0.001)
    assert processed == total_jobs

    records = store.all_records()
    for request_id in request_ids:
        record = records[request_id]
        assert "worker_claimed_at" in record.lifecycle_timestamps
        assert "terminal_at" in record.lifecycle_timestamps
        if request_id in fail_ids:
            assert record.status == "failed"
            assert record.error_code == "prove_failed"
            assert record.error_message
        else:
            assert record.status == "ready"
            assert record.artifact_refs["proof"].endswith(".pf")
            assert record.artifact_refs["public"].endswith("_settings.json")
