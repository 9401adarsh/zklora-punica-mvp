import numpy as np

from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig
from mvp_server.proof.prover_worker import ProverWorker
from mvp_server.proof.zklora_adapter import ZkLoraAdapter
from mvp_server.runtime.model_runtime import InferenceResult


class FakeRuntime:
    loaded = True

    def infer_prefill(self, prompt: str, generation_params=None) -> InferenceResult:
        _ = generation_params
        return InferenceResult(
            output=prompt,
            module_id="transformer.h.0.attn.c_attn",
            h_x="hx",
            h_delta="hd",
            hash_schema_version=1,
            x_pre=np.asarray([[1.0]], dtype=np.float32),
            delta_post=np.asarray([[2.0]], dtype=np.float32),
        )


def test_lifecycle_timestamps_sampled_ready(tmp_path) -> None:
    cfg = AppConfig.from_dict({"artifacts_root": str(tmp_path)})
    server = MVPServer(config=cfg, runtime=FakeRuntime())

    response = server.post_infer({"prompt": "hola"})
    request_id = response["receipt"]["request_id"]

    worker = ProverWorker(
        manifest=server.proof_manifest,
        proof_store=server.proof_store,
        adapter=ZkLoraAdapter(str(tmp_path)),
    )
    assert worker.run_once()

    record = server.proof_store.get(request_id)
    assert record is not None
    ts = record.lifecycle_timestamps
    assert "request_accepted_at" in ts
    assert "sampled_decision_at" in ts
    assert "witness_persisted_at" in ts
    assert "proof_enqueued_at" in ts
    assert "worker_claimed_at" in ts
    assert "terminal_at" in ts
