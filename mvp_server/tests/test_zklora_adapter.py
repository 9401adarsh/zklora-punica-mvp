import pytest

from mvp_server.proof.zklora_adapter import ZkLoraAdapter


def test_zklora_adapter_prove_writes_artifacts(tmp_path) -> None:
    adapter = ZkLoraAdapter(str(tmp_path))
    result = adapter.prove(
        {
            "request_id": "r1",
            "module_id": "m1",
            "witness_ref": "/tmp/witness.json",
        }
    )

    assert result.duration_ms >= 0
    assert result.proof_ref.endswith("proof.json")
    assert result.public_ref.endswith("public.json")


def test_zklora_adapter_force_fail(tmp_path) -> None:
    adapter = ZkLoraAdapter(str(tmp_path))
    with pytest.raises(RuntimeError, match="forced prover failure"):
        adapter.prove(
            {
                "request_id": "r1",
                "module_id": "m1",
                "witness_ref": "/tmp/witness.json",
                "force_fail": True,
            }
        )
