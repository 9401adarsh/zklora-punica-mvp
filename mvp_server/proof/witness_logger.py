from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from mvp_server.schemas import WitnessRecord


@dataclass
class WitnessPacket:
    request_id: str
    module_id: str
    x_pre: np.ndarray
    delta_post: np.ndarray
    h_x: str
    h_delta: str
    hash_schema_version: int


class WitnessLogger:
    """Persists sampled witness tensors and metadata to durable storage."""

    def __init__(self, artifacts_root: str) -> None:
        self.artifacts_root = Path(artifacts_root)

    def persist(self, packet: WitnessPacket) -> WitnessRecord:
        witness_dir = self.artifacts_root / "witness" / packet.request_id / packet.module_id
        witness_dir.mkdir(parents=True, exist_ok=True)

        x_path = witness_dir / "x.npy"
        delta_path = witness_dir / "delta.npy"
        meta_path = witness_dir / "meta.json"

        np.save(x_path, packet.x_pre)
        np.save(delta_path, packet.delta_post)

        record = WitnessRecord(
            request_id=packet.request_id,
            module_id=packet.module_id,
            x_ref=str(x_path),
            delta_ref=str(delta_path),
            meta_ref=str(meta_path),
            h_x=packet.h_x,
            h_delta=packet.h_delta,
            hash_schema_version=packet.hash_schema_version,
        )

        with meta_path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(record), handle, sort_keys=True)

        return record
