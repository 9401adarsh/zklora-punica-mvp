import pytest

from mvp_server.config import AppConfig


def test_default_config_is_valid() -> None:
    cfg = AppConfig.from_dict({})
    assert cfg.base_model_id == "distilgpt2"
    assert cfg.proof_mode == "every_request"
    assert cfg.sample_n is None
    assert cfg.inference_device == "cuda"
    assert cfg.artifacts_root == "/artifacts"


def test_sample_mode_requires_sample_n() -> None:
    with pytest.raises(ValueError, match="sample_n"):
        AppConfig.from_dict({"proof_mode": "sampled"})


def test_every_request_rejects_sample_n() -> None:
    with pytest.raises(ValueError, match="sample_n"):
        AppConfig.from_dict({"proof_mode": "every_request", "sample_n": 4})


def test_resolved_paths_use_artifacts_root() -> None:
    cfg = AppConfig.from_dict({"artifacts_root": "/tmp/a"})
    assert cfg.resolved_proof_manifest_path() == "/tmp/a/proof/proof_jobs.jsonl"
    assert cfg.resolved_proof_claims_path() == "/tmp/a/proof/proof_claims.jsonl"
    assert cfg.resolved_proof_store_path() == "/tmp/a/proof/proof_store.json"


def test_worker_poll_interval_must_be_positive() -> None:
    with pytest.raises(ValueError, match="worker_poll_interval_ms"):
        AppConfig.from_dict({"worker_poll_interval_ms": 0})


def test_inference_device_must_be_supported() -> None:
    with pytest.raises(ValueError, match="inference_device"):
        AppConfig.from_dict({"inference_device": "mps"})
