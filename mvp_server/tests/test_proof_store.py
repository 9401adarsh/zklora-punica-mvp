import pytest

from mvp_server.proof.proof_store import ProofStore


def test_proof_store_valid_transitions() -> None:
    store = ProofStore()
    store.set_status("req-1", "queued", module_id="m1")
    store.set_status("req-1", "pending", module_id="m1")
    store.set_terminal("req-1", "ready", module_id="m1", artifact_refs={"proof": "p"})

    record = store.get("req-1")
    assert record is not None
    assert record.status == "ready"
    assert record.module_ids == ["m1"]
    assert record.artifact_refs["proof"] == "p"


def test_proof_store_rejects_invalid_transition() -> None:
    store = ProofStore()
    store.set_status("req-1", "queued", module_id="m1")
    with pytest.raises(ValueError, match="invalid proof status transition"):
        store.set_status("req-1", "ready", module_id="m1")


def test_proof_store_terminal_passthrough_states() -> None:
    store = ProofStore()
    store.set_status("req-1", "not_sampled", module_id="m1")
    store.set_status("req-1", "not_sampled", module_id="m1")
    record = store.get("req-1")
    assert record is not None
    assert record.status == "not_sampled"
