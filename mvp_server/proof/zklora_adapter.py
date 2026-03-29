from __future__ import annotations

import asyncio
import inspect
import json
import re
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from time import perf_counter
from typing import Any


@dataclass
class ProveResult:
    proof_ref: str
    public_ref: str
    duration_ms: float
    stage_setup_s: float | None = None
    stage_witness_s: float | None = None
    stage_prove_s: float | None = None
    stage_total_s: float | None = None


class ZkLoraAdapter:
    """Single-adapter ZKLoRA proof adapter using direct local APIs."""

    def __init__(
        self,
        artifacts_root: str,
        base_model_id: str = "distilgpt2",
        adapter_id: str = "ng0-k1/distilgpt2-finetuned-es",
        prover_backend: str = "cpu",
        model_loader: Any | None = None,
        exporter: Any | None = None,
        prove_runner: Any | None = None,
    ) -> None:
        backend = str(prover_backend).strip().lower()
        if backend not in {"cpu", "gpu"}:
            raise ValueError("prover_backend must be one of {cpu, gpu}")

        self.artifacts_root = Path(artifacts_root)
        self.base_model_id = base_model_id
        self.adapter_id = adapter_id
        self.prover_backend = backend
        self._peft_model: Any | None = None
        self._model_loader = model_loader
        self._exporter = exporter
        self._prove_runner = prove_runner

    @staticmethod
    def _job_value(job: Any, key: str) -> Any:
        if isinstance(job, dict):
            return job[key]
        return getattr(job, key)

    @staticmethod
    def _strip_prefix(raw_name: str) -> str:
        name = raw_name
        for prefix in ("base_model.model.", "base_model.", "model."):
            if name.startswith(prefix):
                name = name[len(prefix) :]
        return name.strip()

    @staticmethod
    def _safe_component(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
        return cleaned.strip("._") or "default"

    def _setup_dir_for_module(self, module_id: str) -> Path:
        return (
            self.artifacts_root
            / "proof_setup"
            / self._safe_component(self.base_model_id)
            / self._safe_component(self.adapter_id)
            / self._safe_component(module_id)
        )

    @staticmethod
    def _ensure_transformers_peft_compat() -> None:
        import transformers

        if hasattr(transformers, "EncoderDecoderCache"):
            return

        cache_base = getattr(transformers, "Cache", object)

        class EncoderDecoderCache(cache_base):
            pass

        transformers.EncoderDecoderCache = EncoderDecoderCache

    @staticmethod
    def _ensure_zklora_paths() -> None:
        root = Path(__file__).resolve().parents[2]
        candidates = [
            root / "zklora" / "src",
            Path("/workspace/zklora/src"),
            Path("/opt/zkLoRA/src"),
        ]
        for candidate in candidates:
            candidate_str = str(candidate)
            if candidate.exists() and candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)

    @classmethod
    def _import_any(cls, module_names: tuple[str, ...]) -> Any:
        cls._ensure_zklora_paths()
        last_error: Exception | None = None
        for name in module_names:
            try:
                return import_module(name)
            except Exception as exc:  # pragma: no cover - best-effort fallback path
                last_error = exc
        if last_error is None:
            raise RuntimeError("no module names provided")
        raise last_error

    @staticmethod
    def _supports_kwargs(fn: Any, name: str) -> bool:
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        if name in signature.parameters:
            return True
        return any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )

    @staticmethod
    def _is_signature_type_error(exc: TypeError) -> bool:
        text = str(exc)
        return (
            "unexpected keyword argument" in text
            or "required positional argument" in text
            or "positional arguments but" in text
        )

    def _ensure_gpu_runtime_available(self) -> None:
        if self.prover_backend != "gpu":
            return
        try:
            import torch
        except Exception as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "gpu backend requested but torch is unavailable"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError(
                "gpu backend requested but CUDA runtime is unavailable"
            )

    def _load_witness_inputs(self, job: Any) -> tuple[Any, dict[str, Any]]:
        witness_ref = Path(str(self._job_value(job, "witness_ref")))
        if not witness_ref.exists():
            raise ValueError(f"missing witness metadata: {witness_ref}")

        with witness_ref.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)
        if not isinstance(meta, dict):
            raise ValueError("witness metadata must be a JSON object")

        x_ref = meta.get("x_ref")
        if not isinstance(x_ref, str) or not x_ref:
            raise ValueError("witness metadata missing x_ref")

        import numpy as np

        x_pre = np.load(x_ref)
        return x_pre, meta

    def _default_model_loader(self) -> Any:
        self._ensure_transformers_peft_compat()

        from peft import PeftModel
        from transformers import AutoModelForCausalLM

        base_model = AutoModelForCausalLM.from_pretrained(self.base_model_id)
        base_model.config.use_cache = False
        base_model.eval()
        peft_model = PeftModel.from_pretrained(base_model, self.adapter_id)
        peft_model.eval()
        return peft_model

    def _load_or_get_peft_model(self) -> Any:
        if self._peft_model is not None:
            return self._peft_model
        if self._model_loader is None:
            self._peft_model = self._default_model_loader()
            return self._peft_model
        self._peft_model = self._model_loader(self.base_model_id, self.adapter_id)
        return self._peft_model

    def _resolve_target_submodule(self, module_id: str) -> Any:
        peft_model = self._load_or_get_peft_model()
        modules: dict[str, Any] = {}
        for raw_name, module in peft_model.named_modules():
            stripped = self._strip_prefix(str(raw_name))
            if stripped and stripped not in modules:
                modules[stripped] = module
        if module_id not in modules:
            raise ValueError(f"module '{module_id}' not found in PEFT model")

        module = modules[module_id]
        if not hasattr(module, "lora_A") or not hasattr(module, "lora_B"):
            raise ValueError(f"module '{module_id}' does not expose LoRA parameters")
        return module

    def _export_onnx_and_inputs(
        self, module_id: str, x_pre: Any, submodule: Any, proof_dir: Path
    ) -> None:
        proof_dir.mkdir(parents=True, exist_ok=True)
        if self._exporter is None:
            exporter_mod = self._import_any(("zklora.mpi_lora_onnx_exporter",))
            self._exporter = getattr(exporter_mod, "export_lora_onnx_json_mpi")

        self._exporter(
            sub_name=module_id,
            x_data=x_pre,
            submodule=submodule,
            output_dir=str(proof_dir),
            verbose=False,
        )
        if not list(proof_dir.glob("*.onnx")):
            raise ValueError("expected at least one ONNX artifact after export")
        if not list(proof_dir.glob("*.json")):
            raise ValueError("expected at least one JSON artifact after export")

    def _run_zklora_prove(
        self, proof_dir: Path, setup_dir: Path
    ) -> dict[str, float] | None:
        self._ensure_gpu_runtime_available()

        if self._prove_runner is None:
            prove_mod = self._import_any(("zklora.zk_proof_generator",))
            self._prove_runner = getattr(prove_mod, "generate_proofs")

        kwargs: dict[str, Any] = {
            "onnx_dir": str(proof_dir),
            "json_dir": str(proof_dir),
            "output_dir": str(proof_dir),
            "verbose": False,
        }
        if self._supports_kwargs(self._prove_runner, "setup_dir"):
            kwargs["setup_dir"] = str(setup_dir)
        if self._supports_kwargs(self._prove_runner, "backend"):
            kwargs["backend"] = self.prover_backend

        result: Any
        try:
            result = self._prove_runner(**kwargs)
        except TypeError as first_exc:
            if not self._is_signature_type_error(first_exc):
                raise
            fallback_kwargs = {
                "onnx_dir": str(proof_dir),
                "json_dir": str(proof_dir),
                "output_dir": str(proof_dir),
                "setup_dir": str(setup_dir),
                "verbose": False,
            }
            try:
                result = self._prove_runner(**fallback_kwargs)
            except TypeError as second_exc:
                if not self._is_signature_type_error(second_exc):
                    raise
                result = self._prove_runner(
                    onnx_dir=str(proof_dir),
                    json_dir=str(proof_dir),
                    output_dir=str(proof_dir),
                    verbose=False,
                )

        if inspect.isawaitable(result):
            result = asyncio.run(result)
        if result is None:
            raise RuntimeError("proof generation returned no result")
        stage_timings: dict[str, float] | None = None
        if isinstance(result, tuple) and len(result) >= 5:
            if int(result[-1]) < 1:
                raise RuntimeError("proof generation produced zero proofs")
            setup_s = float(result[0])
            witness_s = float(result[1])
            prove_s = float(result[2])
            stage_timings = {
                "setup_s": setup_s,
                "witness_s": witness_s,
                "prove_s": prove_s,
                "total_s": setup_s + witness_s + prove_s,
            }
        return stage_timings

    def _collect_proof_refs(self, proof_dir: Path, setup_dir: Path) -> tuple[str, str]:
        proof_files = sorted(proof_dir.glob("*.pf"))
        if not proof_files:
            raise ValueError("missing proof artifact (*.pf)")

        public_candidates = sorted(proof_dir.glob("*_settings.json"))
        if not public_candidates:
            public_candidates = sorted(proof_dir.glob("*.vk"))
        if not public_candidates:
            public_candidates = sorted(setup_dir.glob("*_settings.json"))
        if not public_candidates:
            public_candidates = sorted(setup_dir.glob("*.vk"))
        if not public_candidates:
            raise ValueError("missing verification artifact (*_settings.json or *.vk)")

        return str(proof_files[0]), str(public_candidates[0])

    def prove(self, job: Any) -> ProveResult:
        if isinstance(job, dict) and job.get("force_fail"):
            raise RuntimeError("prove: forced prover failure")

        request_id = str(self._job_value(job, "request_id"))
        module_id = str(self._job_value(job, "module_id"))

        proof_dir = self.artifacts_root / "proofs" / request_id / module_id
        setup_dir = self._setup_dir_for_module(module_id)
        start = perf_counter()
        try:
            x_pre, _meta = self._load_witness_inputs(job)
        except Exception as exc:
            raise RuntimeError(f"load_witness: {exc}") from exc

        try:
            submodule = self._resolve_target_submodule(module_id)
        except Exception as exc:
            raise RuntimeError(f"resolve_module: {exc}") from exc

        try:
            self._export_onnx_and_inputs(module_id, x_pre, submodule, proof_dir)
        except Exception as exc:
            raise RuntimeError(f"export: {exc}") from exc

        try:
            stage_timings = self._run_zklora_prove(proof_dir, setup_dir)
        except Exception as exc:
            raise RuntimeError(f"prove: {exc}") from exc

        try:
            proof_ref, public_ref = self._collect_proof_refs(proof_dir, setup_dir)
        except Exception as exc:
            raise RuntimeError(f"collect: {exc}") from exc

        return ProveResult(
            proof_ref=proof_ref,
            public_ref=public_ref,
            duration_ms=(perf_counter() - start) * 1000.0,
            stage_setup_s=None if stage_timings is None else stage_timings["setup_s"],
            stage_witness_s=None
            if stage_timings is None
            else stage_timings["witness_s"],
            stage_prove_s=None if stage_timings is None else stage_timings["prove_s"],
            stage_total_s=None if stage_timings is None else stage_timings["total_s"],
        )
