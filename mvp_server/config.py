from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AppConfig:
    base_model_id: str = "distilgpt2"
    adapter_id: str = "ng0-k1/distilgpt2-finetuned-es"
    proof_scope: str = "prefill_only"
    target_module_path: str = "transformer.h.0.attn.c_attn"
    proof_mode: str = "every_request"
    sample_n: Optional[int] = None
    prover_backend: str = "cpu"
    gpu_routing_policy: str = "fallback"
    proof_worker_threads: int = 2
    inference_device: str = "cuda"
    hash_schema_version: int = 1
    artifacts_root: str = "/artifacts"
    proof_manifest_path: Optional[str] = None
    proof_claims_path: Optional[str] = None
    proof_store_path: Optional[str] = None
    worker_poll_interval_ms: int = 250

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        cfg = cls(
            base_model_id=str(data.get("base_model_id", cls.base_model_id)),
            adapter_id=str(data.get("adapter_id", cls.adapter_id)),
            proof_scope=str(data.get("proof_scope", cls.proof_scope)),
            target_module_path=str(
                data.get("target_module_path", cls.target_module_path)
            ),
            proof_mode=str(data.get("proof_mode", cls.proof_mode)),
            sample_n=data.get("sample_n", cls.sample_n),
            prover_backend=str(data.get("prover_backend", cls.prover_backend)),
            gpu_routing_policy=str(
                data.get("gpu_routing_policy", cls.gpu_routing_policy)
            ),
            proof_worker_threads=int(
                data.get("proof_worker_threads", cls.proof_worker_threads)
            ),
            inference_device=str(data.get("inference_device", cls.inference_device)),
            hash_schema_version=int(
                data.get("hash_schema_version", cls.hash_schema_version)
            ),
            artifacts_root=str(data.get("artifacts_root", cls.artifacts_root)),
            proof_manifest_path=data.get("proof_manifest_path", cls.proof_manifest_path),
            proof_claims_path=data.get("proof_claims_path", cls.proof_claims_path),
            proof_store_path=data.get("proof_store_path", cls.proof_store_path),
            worker_poll_interval_ms=int(
                data.get("worker_poll_interval_ms", cls.worker_poll_interval_ms)
            ),
        )
        cfg.validate()
        return cfg

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw_sample_n = os.getenv("MVP_SAMPLE_N")
        sample_n = int(raw_sample_n) if raw_sample_n else None
        data: Dict[str, Any] = {
            "base_model_id": os.getenv("MVP_BASE_MODEL_ID", cls.base_model_id),
            "adapter_id": os.getenv("MVP_ADAPTER_ID", cls.adapter_id),
            "proof_scope": os.getenv("MVP_PROOF_SCOPE", cls.proof_scope),
            "target_module_path": os.getenv(
                "MVP_TARGET_MODULE_PATH", cls.target_module_path
            ),
            "proof_mode": os.getenv("MVP_PROOF_MODE", cls.proof_mode),
            "sample_n": sample_n,
            "prover_backend": os.getenv("MVP_PROVER_BACKEND", cls.prover_backend),
            "gpu_routing_policy": os.getenv(
                "MVP_GPU_ROUTING_POLICY", cls.gpu_routing_policy
            ),
            "proof_worker_threads": int(
                os.getenv("MVP_PROOF_WORKER_THREADS", str(cls.proof_worker_threads))
            ),
            "inference_device": os.getenv("MVP_INFERENCE_DEVICE", cls.inference_device),
            "hash_schema_version": int(
                os.getenv("MVP_HASH_SCHEMA_VERSION", str(cls.hash_schema_version))
            ),
            "artifacts_root": os.getenv("MVP_ARTIFACTS_ROOT", cls.artifacts_root),
            "proof_manifest_path": os.getenv("MVP_PROOF_MANIFEST_PATH"),
            "proof_claims_path": os.getenv("MVP_PROOF_CLAIMS_PATH"),
            "proof_store_path": os.getenv("MVP_PROOF_STORE_PATH"),
            "worker_poll_interval_ms": int(
                os.getenv(
                    "MVP_WORKER_POLL_INTERVAL_MS", str(cls.worker_poll_interval_ms)
                )
            ),
        }
        return cls.from_dict(data)

    def resolved_proof_manifest_path(self) -> str:
        return self.proof_manifest_path or str(
            Path(self.artifacts_root) / "proof" / "proof_jobs.jsonl"
        )

    def resolved_proof_claims_path(self) -> str:
        return self.proof_claims_path or str(
            Path(self.artifacts_root) / "proof" / "proof_claims.jsonl"
        )

    def resolved_proof_store_path(self) -> str:
        return self.proof_store_path or str(
            Path(self.artifacts_root) / "proof" / "proof_store.json"
        )

    def validate(self) -> None:
        if not self.target_module_path:
            raise ValueError("target_module_path is required")
        if self.proof_scope != "prefill_only":
            raise ValueError("proof_scope must be prefill_only in v1")
        if self.proof_mode not in {"every_request", "sampled"}:
            raise ValueError("proof_mode must be one of {every_request, sampled}")
        if self.proof_mode == "sampled" and (self.sample_n is None or self.sample_n < 1):
            raise ValueError("sample_n must be >= 1 when proof_mode=sampled")
        if self.proof_mode == "every_request" and self.sample_n is not None:
            raise ValueError("sample_n must be unset when proof_mode=every_request")
        if self.prover_backend not in {"cpu", "gpu"}:
            raise ValueError("prover_backend must be one of {cpu, gpu}")
        if self.gpu_routing_policy not in {"fallback", "strict"}:
            raise ValueError("gpu_routing_policy must be one of {fallback, strict}")
        if self.proof_worker_threads < 1:
            raise ValueError("proof_worker_threads must be >= 1")
        if self.inference_device not in {"cuda", "cpu"}:
            raise ValueError("inference_device must be one of {cuda, cpu}")
        if self.hash_schema_version != 1:
            raise ValueError("hash_schema_version must be 1 in v1")
        if not self.artifacts_root:
            raise ValueError("artifacts_root must be non-empty")
        if self.worker_poll_interval_ms < 1:
            raise ValueError("worker_poll_interval_ms must be >= 1")
