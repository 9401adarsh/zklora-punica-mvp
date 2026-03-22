import json
from pathlib import Path

import numpy as np
import pytest

from mvp_server.proof.zklora_adapter import ZkLoraAdapter


class FakeLoRAModule:
    lora_A = {"default": object()}
    lora_B = {"default": object()}


class FakePeftModel:
    def __init__(self, with_target: bool = True) -> None:
        self.with_target = with_target

    def named_modules(self):
        if self.with_target:
            return [
                ("base_model.model.transformer.h.0.attn.c_attn", FakeLoRAModule()),
            ]
        return [("base_model.model.transformer.h.0.attn.q_proj", FakeLoRAModule())]


def _write_witness(tmp_path: Path, request_id: str, module_id: str) -> str:
    witness_dir = tmp_path / "witness" / request_id / module_id
    witness_dir.mkdir(parents=True, exist_ok=True)

    x_path = witness_dir / "x.npy"
    delta_path = witness_dir / "delta.npy"
    meta_path = witness_dir / "meta.json"

    np.save(x_path, np.asarray([[1.0, 2.0]], dtype=np.float32))
    np.save(delta_path, np.asarray([[0.1, 0.2]], dtype=np.float32))

    with meta_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "request_id": request_id,
                "module_id": module_id,
                "x_ref": str(x_path),
                "delta_ref": str(delta_path),
                "meta_ref": str(meta_path),
                "h_x": "hx",
                "h_delta": "hd",
                "hash_schema_version": 1,
                "schema_version": 1,
            },
            handle,
            sort_keys=True,
        )
    return str(meta_path)


def test_zklora_adapter_prove_writes_artifacts(tmp_path: Path) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r1"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(onnx_dir, json_dir, output_dir, verbose):
        _ = (onnx_dir, json_dir, verbose)
        Path(output_dir, "transformer_h_0_attn_c_attn.pf").write_text(
            "proof",
            encoding="utf-8",
        )
        Path(output_dir, "transformer_h_0_attn_c_attn_settings.json").write_text(
            json.dumps({"k": 20}),
            encoding="utf-8",
        )
        return (0.1, 0.1, 0.1, 10, 1)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        base_model_id="distilgpt2",
        adapter_id="ng0-k1/distilgpt2-finetuned-es",
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fake_generate_proofs,
    )

    result = adapter.prove(
        {
            "request_id": request_id,
            "module_id": module_id,
            "witness_ref": witness_ref,
        }
    )

    assert result.duration_ms >= 0
    assert result.proof_ref.endswith(".pf")
    assert result.public_ref.endswith("_settings.json")
    assert Path(result.proof_ref).exists()
    assert Path(result.public_ref).exists()


def test_zklora_adapter_collects_public_ref_from_setup_cache(tmp_path: Path) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r_setup"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(onnx_dir, json_dir, output_dir, setup_dir, verbose):
        _ = (onnx_dir, json_dir, verbose)
        Path(output_dir, "transformer_h_0_attn_c_attn.pf").write_text(
            "proof",
            encoding="utf-8",
        )
        Path(setup_dir).mkdir(parents=True, exist_ok=True)
        Path(setup_dir, "transformer_h_0_attn_c_attn_settings.json").write_text(
            json.dumps({"k": 20}),
            encoding="utf-8",
        )
        return (0.1, 0.1, 0.1, 10, 1)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        base_model_id="distilgpt2",
        adapter_id="ng0-k1/distilgpt2-finetuned-es",
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fake_generate_proofs,
    )

    result = adapter.prove(
        {
            "request_id": request_id,
            "module_id": module_id,
            "witness_ref": witness_ref,
        }
    )

    assert result.proof_ref.endswith(".pf")
    assert result.public_ref.endswith("_settings.json")
    assert "/proof_setup/" in result.public_ref
    assert Path(result.proof_ref).exists()
    assert Path(result.public_ref).exists()


def test_zklora_adapter_module_missing_fails(tmp_path: Path) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    witness_ref = _write_witness(tmp_path, request_id="r1", module_id=module_id)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=False),
        exporter=lambda **_kwargs: None,
        prove_runner=lambda **_kwargs: (0.1, 0.1, 0.1, 10, 1),
    )

    with pytest.raises(RuntimeError, match="resolve_module:"):
        adapter.prove(
            {
                "request_id": "r1",
                "module_id": module_id,
                "witness_ref": witness_ref,
            }
        )


def test_zklora_adapter_prove_failure_is_stage_prefixed(tmp_path: Path) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    witness_ref = _write_witness(tmp_path, request_id="r2", module_id=module_id)

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (sub_name, x_data, submodule, verbose)
        Path(output_dir, "dummy.onnx").write_bytes(b"onnx")
        Path(output_dir, "dummy.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fail_generate_proofs(**_kwargs):
        raise RuntimeError("backend failed")

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fail_generate_proofs,
    )

    with pytest.raises(RuntimeError, match="^prove: "):
        adapter.prove(
            {
                "request_id": "r2",
                "module_id": module_id,
                "witness_ref": witness_ref,
            }
        )
