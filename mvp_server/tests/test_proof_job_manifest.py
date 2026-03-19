from pathlib import Path

from mvp_server.proof.proof_job_manifest import ProofJobManifest


def test_manifest_append_and_read(tmp_path: Path) -> None:
    path = tmp_path / "proof_jobs.jsonl"
    manifest = ProofJobManifest(str(path))
    manifest.append({"request_id": "r1", "status": "queued"})
    manifest.append({"request_id": "r2", "status": "pending"})
    rows = list(manifest.iter_records())
    assert len(rows) == 2
    assert rows[0]["request_id"] == "r1"
    assert rows[1]["status"] == "pending"


def test_manifest_claim_and_replay(tmp_path: Path) -> None:
    path = tmp_path / "proof_jobs.jsonl"
    claims = tmp_path / "proof_claims.jsonl"
    manifest = ProofJobManifest(str(path), claims_path=str(claims))
    manifest.append({"request_id": "r1", "module_id": "m1"})
    manifest.append({"request_id": "r2", "module_id": "m1"})

    first = manifest.claim_next()
    assert first is not None
    assert first["request_id"] == "r1"

    remaining = list(manifest.iter_unclaimed())
    assert len(remaining) == 1
    assert remaining[0]["request_id"] == "r2"
