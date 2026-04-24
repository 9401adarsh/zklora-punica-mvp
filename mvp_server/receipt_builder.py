from __future__ import annotations

from mvp_server.schemas import Receipt


def build_receipt(
    request_id: str,
    adapter_id: str,
    module_id: str,
    sampled: bool,
    h_x: str,
    h_delta: str,
    hash_schema_version: int,
    proof_status_hint: str,
) -> Receipt:
    return Receipt(
        request_id=request_id,
        adapter_id=adapter_id,
        module_id=module_id,
        sampled=sampled,
        h_x=h_x,
        h_delta=h_delta,
        hash_schema_version=hash_schema_version,
        proof_status_hint=proof_status_hint,
    )

