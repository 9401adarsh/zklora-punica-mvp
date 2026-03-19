from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Dict, Optional

import numpy as np

from .hashing import hash_tensor
from .hook_capture import HookCapture
from .proof_hook_registry import ProofHookRegistry


@dataclass
class InferenceResult:
    output: str
    module_id: str
    h_x: str
    h_delta: str
    hash_schema_version: int
    x_pre: np.ndarray
    delta_post: np.ndarray


def resolve_module_path(root: Any, module_path: str) -> Any:
    node = root
    for part in module_path.split("."):
        if not part:
            raise ValueError(f"invalid module path segment in '{module_path}'")
        if part.isdigit():
            idx = int(part)
            try:
                node = node[idx]
            except Exception as exc:  # pragma: no cover - message wrapping only
                raise ValueError(
                    f"failed to index segment '{part}' in path '{module_path}'"
                ) from exc
        else:
            if not hasattr(node, part):
                raise ValueError(
                    f"missing attribute segment '{part}' in path '{module_path}'"
                )
            node = getattr(node, part)
    return node


class ModelRuntime:
    """Runs prefill inference with one proof hook capture in phase 1."""

    def __init__(
        self,
        config: Any,
        model: Optional[Any] = None,
        tokenizer: Optional[Any] = None,
        registry: Optional[ProofHookRegistry] = None,
    ) -> None:
        self.config = config
        self.model = model
        self.tokenizer = tokenizer
        self.registry = registry or ProofHookRegistry.single_module(
            config.target_module_path
        )
        self.hook_capture: Optional[HookCapture] = None
        self.device = getattr(config, "inference_device", "cuda")
        self._infer_lock = threading.Lock()
        self._loaded = model is not None and tokenizer is not None

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._loaded:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("inference_device=cuda but CUDA is not available")

        self.model = AutoModelForCausalLM.from_pretrained(self.config.base_model_id)
        self.model = self.model.to(self.device)
        self.model.eval()
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.base_model_id)
        self._loaded = True

    def _ensure_hook_registered(self) -> None:
        if not self._loaded:
            raise RuntimeError("model runtime must be loaded before infer")
        if self.hook_capture is not None:
            return
        spec = self.registry.active_spec()
        target_module = resolve_module_path(self.model, spec.module_path)
        self.hook_capture = HookCapture(module_id=spec.module_id)
        self.hook_capture.attach(target_module)

    def infer_prefill(
        self, prompt: str, generation_params: Optional[Dict[str, Any]] = None
    ) -> InferenceResult:
        _ = generation_params
        # HookCapture stores request-local tensors in shared instance fields.
        # Serialize prefill forward pass + pop to avoid cross-request races.
        with self._infer_lock:
            self.load()
            self._ensure_hook_registered()

            encoded = self.tokenizer(prompt, return_tensors="pt")
            encoded = {
                key: value.to(self.device) if hasattr(value, "to") else value
                for key, value in encoded.items()
            }
            _ = self.model(**encoded)
            capture = self.hook_capture.pop_capture()

            h_x, x_pre = hash_tensor(
                capture.x_pre, schema_version=self.config.hash_schema_version
            )
            h_delta, delta_post = hash_tensor(
                capture.delta_post, schema_version=self.config.hash_schema_version
            )
            output_text = self.tokenizer.decode(
                encoded["input_ids"][0].detach().cpu(), skip_special_tokens=True
            )
            return InferenceResult(
                output=output_text,
                module_id=capture.module_id,
                h_x=h_x,
                h_delta=h_delta,
                hash_schema_version=self.config.hash_schema_version,
                x_pre=x_pre,
                delta_post=delta_post,
            )
