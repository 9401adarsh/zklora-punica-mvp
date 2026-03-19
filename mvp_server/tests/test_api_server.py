import numpy as np

from mvp_server.api.server import ApiError, MVPServer
from mvp_server.config import AppConfig
from mvp_server.proof.sampling_policy import SamplingPolicy
from mvp_server.proof.witness_logger import WitnessLogger
from mvp_server.runtime.model_runtime import InferenceResult


class FakeRuntime:
    loaded = True

    def infer_prefill(self, prompt: str, generation_params=None) -> InferenceResult:
        _ = generation_params
        return InferenceResult(
            output=f"echo:{prompt}",
            module_id="transformer.h.0.attn.c_attn",
            h_x="abc123",
            h_delta="def456",
            hash_schema_version=1,
            x_pre=np.asarray([[1.0, 2.0]], dtype=np.float32),
            delta_post=np.asarray([[0.1, 0.2]], dtype=np.float32),
        )


class NeverSamplePolicy:
    def should_sample(self, _request_id: str, _module_id: str) -> bool:
        return False


class BrokenWitnessLogger(WitnessLogger):
    def persist(self, packet):  # type: ignore[override]
        raise RuntimeError("queue overloaded")


def test_post_infer_returns_receipt_and_queued_status(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(config=cfg, runtime=FakeRuntime())
    response = server.post_infer({"prompt": "hola"})
    assert response["output"] == "echo:hola"
    assert "receipt" in response
    assert response["receipt"]["H_x"] == "abc123"
    assert response["receipt"]["H_delta"] == "def456"
    assert response["receipt"]["proof_status_hint"] == "queued"

    request_id = response["receipt"]["request_id"]
    status, body = server.get_proof(request_id)
    assert status == 202
    assert body["status"] == "queued"


def test_post_infer_unsampled_sets_not_sampled(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(
        config=cfg,
        runtime=FakeRuntime(),
        sampling_policy=NeverSamplePolicy(),
    )
    response = server.post_infer({"prompt": "hola"})
    assert response["receipt"]["proof_status_hint"] == "not_sampled"


def test_post_infer_persist_failure_sets_dropped_overload(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(
        config=cfg,
        runtime=FakeRuntime(),
        sampling_policy=SamplingPolicy(mode="every_request"),
        witness_logger=BrokenWitnessLogger(str(tmp_path)),
    )
    response = server.post_infer({"prompt": "hola"})
    assert response["receipt"]["proof_status_hint"] == "dropped_overload"


def test_post_infer_rejects_unapproved_adapter(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(config=cfg, runtime=FakeRuntime())
    try:
        server.post_infer({"prompt": "hola", "adapter_id": "wrong/adapter"})
        assert False, "expected ApiError"
    except ApiError as exc:
        assert exc.status_code == 400
        assert exc.code == "adapter_not_allowed"
