import json
import sys
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


def test_zklora_adapter_backend_is_forwarded_when_supported(tmp_path: Path) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r_backend"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    observed_backend = {"value": None}

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(
        onnx_dir, json_dir, output_dir, setup_dir, backend, verbose
    ):
        _ = (onnx_dir, json_dir, setup_dir, verbose)
        observed_backend["value"] = backend
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
        prover_backend="cpu",
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
    assert observed_backend["value"] == "cpu"
    assert result.stage_setup_s == pytest.approx(0.1)
    assert result.stage_witness_s == pytest.approx(0.1)
    assert result.stage_prove_s == pytest.approx(0.1)
    assert result.stage_total_s == pytest.approx(0.3)


def test_zklora_adapter_gpu_backend_fails_fast_without_cuda(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r_gpu"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class FakeTorch:
        cuda = FakeCuda()

    monkeypatch.setitem(sys.modules, "torch", FakeTorch())

    called = {"value": False}

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(**_kwargs):
        called["value"] = True
        return (0.1, 0.1, 0.1, 10, 1)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        prover_backend="gpu",
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fake_generate_proofs,
    )

    with pytest.raises(RuntimeError, match="^prove: gpu backend requested"):
        adapter.prove(
            {
                "request_id": request_id,
                "module_id": module_id,
                "witness_ref": witness_ref,
            }
        )
    assert called["value"] is False


def test_zklora_adapter_rejects_invalid_backend(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="prover_backend"):
        ZkLoraAdapter(artifacts_root=str(tmp_path), prover_backend="tpu")


def test_zklora_adapter_rejects_invalid_gpu_routing_policy(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="gpu_routing_policy"):
        ZkLoraAdapter(
            artifacts_root=str(tmp_path),
            prover_backend="gpu",
            gpu_routing_policy="invalid",
        )


def test_zklora_adapter_gpu_routing_strict_fails_when_unroutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r_gpu_strict"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

    class FakeTorch:
        cuda = FakeCuda()

    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    monkeypatch.setattr(ZkLoraAdapter, "_ezkl_prove_supports_backend", lambda self: False)

    called = {"value": False}

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(onnx_dir, json_dir, output_dir, setup_dir, verbose):
        _ = (onnx_dir, json_dir, output_dir, setup_dir, verbose)
        called["value"] = True
        return (0.1, 0.1, 0.1, 10, 1)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        prover_backend="gpu",
        gpu_routing_policy="strict",
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fake_generate_proofs,
    )

    with pytest.raises(RuntimeError, match="^prove: gpu routing unsupported"):
        adapter.prove(
            {
                "request_id": request_id,
                "module_id": module_id,
                "witness_ref": witness_ref,
            }
        )
    assert called["value"] is False


def test_zklora_adapter_gpu_routing_fallback_marks_cpu_effective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r_gpu_fallback"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

    class FakeTorch:
        cuda = FakeCuda()

    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    monkeypatch.setattr(ZkLoraAdapter, "_ezkl_prove_supports_backend", lambda self: False)

    observed_backend = {"value": None}

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(onnx_dir, json_dir, output_dir, setup_dir, verbose):
        _ = (onnx_dir, json_dir, setup_dir, verbose)
        observed_backend["value"] = None
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
        prover_backend="gpu",
        gpu_routing_policy="fallback",
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

    assert observed_backend["value"] is None
    assert result.backend_intent == "gpu"
    assert result.backend_effective == "cpu"
    assert result.backend_routing_supported is False
    assert result.backend_fallback_used is True
    assert "policy=fallback" in str(result.backend_routing_reason)


def test_zklora_adapter_gpu_routing_supported_marks_gpu_effective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    request_id = "r_gpu_supported"
    witness_ref = _write_witness(tmp_path, request_id=request_id, module_id=module_id)

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return True

    class FakeTorch:
        cuda = FakeCuda()

    monkeypatch.setitem(sys.modules, "torch", FakeTorch())
    monkeypatch.setattr(ZkLoraAdapter, "_ezkl_prove_supports_backend", lambda self: True)

    observed_backend = {"value": None}

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(
        onnx_dir, json_dir, output_dir, setup_dir, backend, verbose
    ):
        _ = (onnx_dir, json_dir, setup_dir, verbose)
        observed_backend["value"] = backend
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
        prover_backend="gpu",
        gpu_routing_policy="strict",
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

    assert observed_backend["value"] == "gpu"
    assert result.backend_intent == "gpu"
    assert result.backend_effective == "gpu"
    assert result.backend_routing_supported is True
    assert result.backend_fallback_used is False


def test_zklora_adapter_setup_cache_hits_after_first_build(tmp_path: Path) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    cache_root = tmp_path / "setup-cache"

    witness_ref_1 = _write_witness(tmp_path, request_id="r-cache-1", module_id=module_id)
    witness_ref_2 = _write_witness(tmp_path, request_id="r-cache-2", module_id=module_id)

    observed_pk_exists: list[bool] = []
    observed_setup_dirs: list[str] = []

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(
        onnx_dir,
        json_dir,
        output_dir,
        setup_dir,
        backend,
        verbose,
    ):
        _ = (onnx_dir, json_dir, backend, verbose)
        base = "transformer_h_0_attn_c_attn"
        setup_path = Path(setup_dir)
        setup_path.mkdir(parents=True, exist_ok=True)
        observed_pk_exists.append((setup_path / f"{base}.pk").exists())
        observed_setup_dirs.append(str(setup_path))

        Path(setup_path, f"{base}.ezkl").write_text("circuit", encoding="utf-8")
        Path(setup_path, f"{base}_settings.json").write_text(
            json.dumps({"k": 20}),
            encoding="utf-8",
        )
        Path(setup_path, "kzg.srs").write_text("srs", encoding="utf-8")
        Path(setup_path, f"{base}.vk").write_text("vk", encoding="utf-8")
        Path(setup_path, f"{base}.pk").write_text("pk", encoding="utf-8")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        Path(out, f"{base}.pf").write_text("proof", encoding="utf-8")
        return (0.1, 0.1, 0.1, 10, 1)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        prover_backend="cpu",
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fake_generate_proofs,
        setup_cache_root=str(cache_root),
    )

    result_1 = adapter.prove(
        {
            "request_id": "r-cache-1",
            "module_id": module_id,
            "witness_ref": witness_ref_1,
        }
    )
    result_2 = adapter.prove(
        {
            "request_id": "r-cache-2",
            "module_id": module_id,
            "witness_ref": witness_ref_2,
        }
    )

    assert result_1.setup_cache_enabled is True
    assert result_1.setup_cache_hit is False
    assert result_2.setup_cache_enabled is True
    assert result_2.setup_cache_hit is True
    assert result_1.setup_cache_key == result_2.setup_cache_key
    assert observed_pk_exists == [False, True]
    assert observed_setup_dirs[0] == observed_setup_dirs[1]
    assert Path(observed_setup_dirs[0], "setup_cache_meta.json").exists()


def test_zklora_adapter_setup_cache_fingerprint_change_forces_miss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_id = "transformer.h.0.attn.c_attn"
    cache_root = tmp_path / "setup-cache"

    witness_ref_1 = _write_witness(tmp_path, request_id="r-fp-1", module_id=module_id)
    witness_ref_2 = _write_witness(tmp_path, request_id="r-fp-2", module_id=module_id)

    observed_setup_dirs: list[str] = []
    observed_pk_exists: list[bool] = []

    version_holder = {"value": "v1"}

    def fake_ezkl_version(self) -> str:
        return version_holder["value"]

    monkeypatch.setattr(ZkLoraAdapter, "_ezkl_version", fake_ezkl_version)

    def fake_export(sub_name, x_data, submodule, output_dir, verbose):
        _ = (x_data, submodule, verbose)
        safe_name = sub_name.replace(".", "_").replace("/", "_")
        Path(output_dir, f"{safe_name}.onnx").write_bytes(b"onnx")
        Path(output_dir, f"{safe_name}.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(
        onnx_dir,
        json_dir,
        output_dir,
        setup_dir,
        backend,
        verbose,
    ):
        _ = (onnx_dir, json_dir, backend, verbose)
        base = "transformer_h_0_attn_c_attn"
        setup_path = Path(setup_dir)
        setup_path.mkdir(parents=True, exist_ok=True)
        observed_setup_dirs.append(str(setup_path))
        observed_pk_exists.append((setup_path / f"{base}.pk").exists())

        Path(setup_path, f"{base}.ezkl").write_text("circuit", encoding="utf-8")
        Path(setup_path, f"{base}_settings.json").write_text(
            json.dumps({"k": 20}),
            encoding="utf-8",
        )
        Path(setup_path, "kzg.srs").write_text("srs", encoding="utf-8")
        Path(setup_path, f"{base}.vk").write_text("vk", encoding="utf-8")
        Path(setup_path, f"{base}.pk").write_text("pk", encoding="utf-8")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        Path(out, f"{base}.pf").write_text("proof", encoding="utf-8")
        return (0.1, 0.1, 0.1, 10, 1)

    adapter = ZkLoraAdapter(
        artifacts_root=str(tmp_path),
        prover_backend="cpu",
        model_loader=lambda _base_model_id, _adapter_id: FakePeftModel(with_target=True),
        exporter=fake_export,
        prove_runner=fake_generate_proofs,
        setup_cache_root=str(cache_root),
    )

    result_1 = adapter.prove(
        {
            "request_id": "r-fp-1",
            "module_id": module_id,
            "witness_ref": witness_ref_1,
        }
    )

    version_holder["value"] = "v2"

    result_2 = adapter.prove(
        {
            "request_id": "r-fp-2",
            "module_id": module_id,
            "witness_ref": witness_ref_2,
        }
    )

    assert result_1.setup_cache_hit is False
    assert result_2.setup_cache_hit is False
    assert result_1.setup_cache_key != result_2.setup_cache_key
    assert observed_pk_exists == [False, False]
    assert observed_setup_dirs[0] != observed_setup_dirs[1]
