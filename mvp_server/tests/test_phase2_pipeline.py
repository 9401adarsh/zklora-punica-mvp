import numpy as np

from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig
from mvp_server.proof.prover_worker import ProverWorker
from mvp_server.proof.zklora_adapter import ProveResult
from mvp_server.runtime.model_runtime import InferenceResult


class FakeRuntime:
    loaded = True

    def infer_prefill(self, prompt: str, generation_params=None) -> InferenceResult:
        _ = generation_params
        return InferenceResult(
            output=f"echo:{prompt}",
            module_id="transformer.h.0.attn.c_attn",
            h_x="hx",
            h_delta="hd",
            hash_schema_version=1,
            x_pre=np.asarray([[1.0, 2.0]], dtype=np.float32),
            delta_post=np.asarray([[0.1, 0.2]], dtype=np.float32),
        )


class ReadyAdapter:
    def prove(self, _job):
        return ProveResult(
            proof_ref="/tmp/proof.pf",
            public_ref="/tmp/proof_settings.json",
            duration_ms=1.0,
        )


def test_sampled_request_queued_then_ready(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(config=cfg, runtime=FakeRuntime())

    response = server.post_infer({"prompt": "hola"})
    request_id = response["receipt"]["request_id"]
    status_code, proof_body = server.get_proof(request_id)
    assert status_code == 202
    assert proof_body["status"] == "queued"

    worker = ProverWorker(
        manifest=server.proof_manifest,
        proof_store=server.proof_store,
        adapter=ReadyAdapter(),
    )
    assert worker.run_once()

    status_code, proof_body = server.get_proof(request_id)
    assert status_code == 200
    assert proof_body["status"] == "ready"


def test_get_proof_unknown_returns_404(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(config=cfg, runtime=FakeRuntime())
    status_code, body = server.get_proof("missing")
    assert status_code == 404
    assert body["status"] == "unknown"
