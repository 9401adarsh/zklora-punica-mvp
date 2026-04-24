from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple

from mvp_server.config import AppConfig
from mvp_server.metrics.metrics import MetricsRegistry
from mvp_server.proof.proof_job_manifest import ProofJobManifest
from mvp_server.proof.proof_store import ProofStore
from mvp_server.proof.sampling_policy import SamplingPolicy
from mvp_server.proof.witness_logger import WitnessLogger, WitnessPacket
from mvp_server.receipt_builder import build_receipt
from mvp_server.runtime.model_runtime import ModelRuntime
from mvp_server.schemas import ProofJob


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {"error": self.code, "message": self.message}


class MVPServer:
    """Phase 2 server surface with callable endpoint methods."""

    def __init__(
        self,
        config: AppConfig,
        runtime: Optional[ModelRuntime] = None,
        proof_store: Optional[ProofStore] = None,
        sampling_policy: Optional[SamplingPolicy] = None,
        metrics: Optional[MetricsRegistry] = None,
        witness_logger: Optional[WitnessLogger] = None,
        proof_manifest: Optional[ProofJobManifest] = None,
    ) -> None:
        self.config = config
        self.runtime = runtime or ModelRuntime(config=config)
        self.proof_store = proof_store or ProofStore(path=config.resolved_proof_store_path())
        self.sampling_policy = sampling_policy or SamplingPolicy(
            mode=config.proof_mode,
            sample_n=config.sample_n,
        )
        self.metrics = metrics or MetricsRegistry()
        self.witness_logger = witness_logger or WitnessLogger(config.artifacts_root)
        self.proof_manifest = proof_manifest or ProofJobManifest(
            path=config.resolved_proof_manifest_path(),
            claims_path=config.resolved_proof_claims_path(),
        )

    def post_infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        started_at = time.time()
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise ApiError(400, "invalid_prompt", "prompt must be a non-empty string")

        adapter_id = payload.get("adapter_id", self.config.adapter_id)
        if adapter_id != self.config.adapter_id:
            raise ApiError(
                400,
                "adapter_not_allowed",
                "adapter_id does not match configured baseline adapter",
            )

        request_id = str(uuid.uuid4())
        generation_params = payload.get("generation_params", {})
        result = self.runtime.infer_prefill(prompt, generation_params=generation_params)

        sampled_decision_at = time.time()
        sampled = self.sampling_policy.should_sample(request_id, result.module_id)
        proof_status_hint = "not_sampled"

        if sampled:
            packet = WitnessPacket(
                request_id=request_id,
                module_id=result.module_id,
                x_pre=result.x_pre,
                delta_post=result.delta_post,
                h_x=result.h_x,
                h_delta=result.h_delta,
                hash_schema_version=result.hash_schema_version,
            )
            try:
                witness_record = self.witness_logger.persist(packet)
                persisted_at = time.time()
                proof_job = ProofJob(
                    request_id=request_id,
                    module_id=result.module_id,
                    witness_ref=witness_record.meta_ref,
                    h_x=result.h_x,
                    h_delta=result.h_delta,
                    hash_schema_version=result.hash_schema_version,
                )
                self.proof_manifest.append_job(asdict(proof_job))
                enqueued_at = time.time()
                proof_status_hint = "queued"
                self.proof_store.set_status(
                    request_id=request_id,
                    status=proof_status_hint,
                    module_id=result.module_id,
                    event_at=enqueued_at,
                    lifecycle_key="proof_enqueued_at",
                )
                self.proof_store.annotate_timestamps(
                    request_id,
                    request_accepted_at=started_at,
                    sampled_decision_at=sampled_decision_at,
                    witness_persisted_at=persisted_at,
                )
                self.metrics.inc("proof_sampled_total")
            except Exception:
                dropped_at = time.time()
                proof_status_hint = "dropped_overload"
                self.proof_store.set_status(
                    request_id=request_id,
                    status=proof_status_hint,
                    module_id=result.module_id,
                    event_at=dropped_at,
                    lifecycle_key="dropped_overload_at",
                )
                self.proof_store.annotate_timestamps(
                    request_id,
                    request_accepted_at=started_at,
                    sampled_decision_at=sampled_decision_at,
                )
                self.metrics.inc("proof_dropped_overload_total")
        else:
            unsampled_at = time.time()
            self.proof_store.set_status(
                request_id=request_id,
                status=proof_status_hint,
                module_id=result.module_id,
                event_at=unsampled_at,
                lifecycle_key="not_sampled_at",
            )
            self.proof_store.annotate_timestamps(
                request_id,
                request_accepted_at=started_at,
                sampled_decision_at=sampled_decision_at,
            )
            self.metrics.inc("proof_not_sampled_total")

        infer_latency_ms = (time.time() - started_at) * 1000.0
        self.metrics.inc("infer_requests_total")
        self.metrics.observe("infer_latency_ms", infer_latency_ms)
        self.metrics.set_gauge("proof_manifest_total", float(self.proof_manifest.total_count()))
        self.metrics.set_gauge(
            "proof_manifest_unclaimed", float(self.proof_manifest.unclaimed_count())
        )

        receipt = build_receipt(
            request_id=request_id,
            adapter_id=self.config.adapter_id,
            module_id=result.module_id,
            sampled=sampled,
            h_x=result.h_x,
            h_delta=result.h_delta,
            hash_schema_version=result.hash_schema_version,
            proof_status_hint=proof_status_hint,
        )
        return {"output": result.output, "receipt": receipt.to_dict()}

    def get_proof(self, request_id: str) -> Tuple[int, Dict[str, Any]]:
        record = self.proof_store.get(request_id)
        if record is None:
            return 404, {"status": "unknown"}
        status_code = 202 if record.status in {"queued", "pending"} else 200
        return status_code, asdict(record)

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "model_loaded": self.runtime.loaded,
        }

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.snapshot()
