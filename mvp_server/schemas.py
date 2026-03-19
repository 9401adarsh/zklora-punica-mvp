from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


ProofStatus = str


@dataclass
class Receipt:
    request_id: str
    adapter_id: str
    module_id: str
    sampled: bool
    h_x: str
    h_delta: str
    hash_schema_version: int
    proof_status_hint: ProofStatus
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["H_x"] = payload.pop("h_x")
        payload["H_delta"] = payload.pop("h_delta")
        return payload


@dataclass
class WitnessRecord:
    request_id: str
    module_id: str
    x_ref: str
    delta_ref: str
    meta_ref: str
    h_x: str
    h_delta: str
    hash_schema_version: int
    schema_version: int = 1


@dataclass
class ProofJob:
    request_id: str
    module_id: str
    witness_ref: str
    h_x: str
    h_delta: str
    hash_schema_version: int
    schema_version: int = 1


@dataclass
class ProofRecord:
    request_id: str
    status: ProofStatus
    module_ids: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    artifact_refs: Dict[str, str] = field(default_factory=dict)
    lifecycle_timestamps: Dict[str, float] = field(default_factory=dict)
    schema_version: int = 1
