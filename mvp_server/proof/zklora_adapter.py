from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


@dataclass
class ProveResult:
    proof_ref: str
    public_ref: str
    duration_ms: float


class ZkLoraAdapter:
    """Deterministic fake-proof adapter for Phase-2 CPU integration."""

    def __init__(self, artifacts_root: str) -> None:
        self.artifacts_root = Path(artifacts_root)

    def prove(self, job: Any) -> ProveResult:
        if isinstance(job, dict) and job.get("force_fail"):
            raise RuntimeError("forced prover failure")

        request_id = job["request_id"] if isinstance(job, dict) else job.request_id
        module_id = job["module_id"] if isinstance(job, dict) else job.module_id
        witness_ref = job["witness_ref"] if isinstance(job, dict) else job.witness_ref
        digest = hashlib.sha256(f"{request_id}:{module_id}:{witness_ref}".encode("utf-8")).hexdigest()

        proof_dir = self.artifacts_root / "proofs" / request_id / module_id
        proof_dir.mkdir(parents=True, exist_ok=True)
        proof_path = proof_dir / "proof.json"
        public_path = proof_dir / "public.json"

        start = perf_counter()
        with proof_path.open("w", encoding="utf-8") as handle:
            json.dump({"proof": f"fake-proof-{digest}"}, handle, sort_keys=True)
        with public_path.open("w", encoding="utf-8") as handle:
            json.dump({"public_inputs": [digest[:16], digest[16:32]]}, handle, sort_keys=True)
        duration_ms = (perf_counter() - start) * 1000.0

        return ProveResult(
            proof_ref=str(proof_path),
            public_ref=str(public_path),
            duration_ms=duration_ms,
        )
