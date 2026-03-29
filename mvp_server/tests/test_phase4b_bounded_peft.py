import json
import time
from pathlib import Path

import pytest

from bench import phase4b_bounded_peft as harness


def test_expand_cases_preserves_matrix_order() -> None:
    cases = harness.expand_cases(
        backends=["cpu", "gpu"],
        threads=[1, 2],
        requests=[5, 20],
    )
    tags = [case.tag() for case in cases]
    assert tags == [
        "backend-cpu-threads-1-requests-5",
        "backend-cpu-threads-1-requests-20",
        "backend-cpu-threads-2-requests-5",
        "backend-cpu-threads-2-requests-20",
        "backend-gpu-threads-1-requests-5",
        "backend-gpu-threads-1-requests-20",
        "backend-gpu-threads-2-requests-5",
        "backend-gpu-threads-2-requests-20",
    ]


def test_render_summary_markdown_contains_comparison_sections() -> None:
    payload = {
        "run_dir": "/tmp/r",
        "timeout_sec": 100,
        "request_concurrency": 1,
        "points": [
            {
                "backend": "cpu",
                "threads": 1,
                "requests": 5,
                "status": "completed",
                "status_counts": {"ready": 5},
                "worker_wall_s": 1.0,
                "req_per_sec": 5.0,
                "stage_timing_s": {
                    "setup": {"avg": 0.1},
                    "witness": {"avg": 0.2},
                    "prove": {"avg": 0.3},
                    "total": {"avg": 0.6},
                },
            },
            {
                "backend": "cpu",
                "threads": 2,
                "requests": 5,
                "status": "completed",
                "status_counts": {"ready": 5},
                "worker_wall_s": 0.5,
                "req_per_sec": 10.0,
                "stage_timing_s": {
                    "setup": {"avg": 0.1},
                    "witness": {"avg": 0.2},
                    "prove": {"avg": 0.3},
                    "total": {"avg": 0.6},
                },
            },
            {
                "backend": "gpu",
                "threads": 1,
                "requests": 5,
                "status": "completed",
                "status_counts": {"ready": 5},
                "worker_wall_s": 0.8,
                "req_per_sec": 6.25,
                "stage_timing_s": {
                    "setup": {"avg": 0.1},
                    "witness": {"avg": 0.2},
                    "prove": {"avg": 0.3},
                    "total": {"avg": 0.6},
                },
            },
        ],
    }
    summary_md = harness.render_summary_markdown(payload)
    assert "All Points" in summary_md
    assert "Thread Scaling (Fixed Backend + Requests)" in summary_md
    assert "Backend Delta (Fixed Threads + Requests)" in summary_md


def test_run_case_bounded_marks_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_run_case_direct(*_args, **_kwargs):
        time.sleep(0.5)
        return {}

    monkeypatch.setattr(harness, "run_case_direct", slow_run_case_direct)
    case = harness.BenchmarkCase(backend="cpu", threads=1, requests=1)
    result = harness.run_case_bounded(
        case=case,
        run_dir=tmp_path,
        timeout_sec=1e-3,
        prompt="x",
        request_concurrency=1,
        seed=1,
        hidden_dim=768,
        seq_len=1,
    )
    assert result["status"] == "timed_out"


def test_run_case_direct_full_peft_path_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader_called = {"count": 0}

    class FakeLoRAModule:
        lora_A = {"default": object()}
        lora_B = {"default": object()}

    class FakePeftModel:
        def named_modules(self):
            return [("base_model.model.transformer.h.0.attn.c_attn", FakeLoRAModule())]

    def fake_default_model_loader(self):
        loader_called["count"] += 1
        return FakePeftModel()

    def fake_export_lora_onnx_json_mpi(sub_name, x_data, submodule, output_dir, verbose):
        _ = (sub_name, x_data, submodule, verbose)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "transformer_h_0_attn_c_attn.onnx").write_bytes(b"onnx")
        (out / "transformer_h_0_attn_c_attn.json").write_text(
            json.dumps({"input_data": [[1.0]]}),
            encoding="utf-8",
        )

    async def fake_generate_proofs(onnx_dir, json_dir, output_dir, setup_dir=None, backend="cpu", verbose=False):
        _ = (onnx_dir, json_dir, setup_dir, backend, verbose)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "transformer_h_0_attn_c_attn.pf").write_text("proof", encoding="utf-8")
        (out / "transformer_h_0_attn_c_attn_settings.json").write_text(
            json.dumps({"k": 20}),
            encoding="utf-8",
        )
        return (0.01, 0.02, 0.03, 10, 1)

    class FakeExporterModule:
        export_lora_onnx_json_mpi = staticmethod(fake_export_lora_onnx_json_mpi)

    class FakeProveModule:
        generate_proofs = staticmethod(fake_generate_proofs)

    @classmethod
    def fake_import_any(cls, module_names):
        if module_names == ("zklora.mpi_lora_onnx_exporter",):
            return FakeExporterModule
        if module_names == ("zklora.zk_proof_generator",):
            return FakeProveModule
        raise RuntimeError(f"unexpected import request: {module_names}")

    monkeypatch.setattr(harness.ZkLoraAdapter, "_default_model_loader", fake_default_model_loader)
    monkeypatch.setattr(harness.ZkLoraAdapter, "_import_any", fake_import_any)

    case = harness.BenchmarkCase(backend="cpu", threads=1, requests=2)
    result = harness.run_case_direct(
        case=case,
        case_dir=tmp_path / "case",
        prompt="p",
        request_concurrency=1,
        seed=1,
        hidden_dim=768,
        seq_len=1,
    )
    assert result["status"] == "completed"
    assert result["status_counts"]["ready"] == 2
    assert loader_called["count"] >= 1
    assert result["stage_timing_s"]["total"]["count"] == 2
