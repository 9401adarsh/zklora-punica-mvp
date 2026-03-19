from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from mvp_server.schemas import ProofRecord


_ALLOWED_TRANSITIONS = {
    "queued": {"pending"},
    "pending": {"ready", "failed"},
    "ready": {"ready"},
    "failed": {"failed"},
    "not_sampled": {"not_sampled"},
    "dropped_overload": {"dropped_overload"},
}


class ProofStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self._records: Dict[str, ProofRecord] = {}
        self._path = Path(path) if path else None
        self._lock = Lock()
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        for request_id, payload in raw.get("records", {}).items():
            self._records[request_id] = ProofRecord(**payload)

    def _persist(self) -> None:
        if self._path is None:
            return
        payload = {"records": {k: asdict(v) for k, v in self._records.items()}}
        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        tmp_path.replace(self._path)

    def _check_transition(self, previous: Optional[str], new_status: str) -> None:
        if previous is None:
            if new_status in {"queued", "not_sampled", "dropped_overload"}:
                return
            raise ValueError(f"invalid initial proof status transition to '{new_status}'")
        if new_status not in _ALLOWED_TRANSITIONS.get(previous, set()):
            raise ValueError(f"invalid proof status transition: {previous} -> {new_status}")

    def set_status(
        self,
        request_id: str,
        status: str,
        module_id: Optional[str] = None,
        event_at: Optional[float] = None,
        lifecycle_key: Optional[str] = None,
    ) -> None:
        timestamp = time.time() if event_at is None else float(event_at)
        with self._lock:
            existing = self._records.get(request_id)
            previous = existing.status if existing else None
            self._check_transition(previous, status)

            if existing is None:
                module_ids = [module_id] if module_id else []
                self._records[request_id] = ProofRecord(
                    request_id=request_id,
                    status=status,
                    module_ids=module_ids,
                )
                existing = self._records[request_id]
            else:
                existing.status = status
                if module_id and module_id not in existing.module_ids:
                    existing.module_ids.append(module_id)

            if lifecycle_key:
                existing.lifecycle_timestamps[lifecycle_key] = timestamp
            if status == "pending":
                existing.lifecycle_timestamps.setdefault("worker_claimed_at", timestamp)
            if status in {"not_sampled", "dropped_overload"}:
                existing.lifecycle_timestamps.setdefault("terminal_at", timestamp)

            self._persist()

    def set_terminal(
        self,
        request_id: str,
        status: str,
        module_id: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        artifact_refs: Optional[dict[str, str]] = None,
        event_at: Optional[float] = None,
        lifecycle_key: Optional[str] = None,
    ) -> None:
        timestamp = time.time() if event_at is None else float(event_at)
        with self._lock:
            existing = self._records.get(request_id)
            previous = existing.status if existing else None
            self._check_transition(previous, status)
            if existing is None:
                raise ValueError(f"missing proof record for request_id='{request_id}'")

            existing.status = status
            if module_id and module_id not in existing.module_ids:
                existing.module_ids.append(module_id)
            if error_code is not None:
                existing.error_code = error_code
            if error_message is not None:
                existing.error_message = error_message
            if artifact_refs:
                existing.artifact_refs.update(artifact_refs)
            existing.lifecycle_timestamps["terminal_at"] = timestamp
            if lifecycle_key:
                existing.lifecycle_timestamps[lifecycle_key] = timestamp
            self._persist()

    def annotate_timestamps(self, request_id: str, **timestamps: float) -> None:
        with self._lock:
            existing = self._records.get(request_id)
            if existing is None:
                return
            for key, value in timestamps.items():
                existing.lifecycle_timestamps[key] = float(value)
            self._persist()

    def get(self, request_id: str) -> Optional[ProofRecord]:
        with self._lock:
            return self._records.get(request_id)

    def all_records(self) -> Dict[str, ProofRecord]:
        with self._lock:
            return dict(self._records)
