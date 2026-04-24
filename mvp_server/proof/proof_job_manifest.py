from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


class ProofJobManifest:
    """Append-only JSONL manifest plus claim log for durable proof job handoff."""

    def __init__(self, path: str, claims_path: Optional[str] = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.claims_path = Path(claims_path) if claims_path else self.path.with_name(
            "proof_claims.jsonl"
        )
        self.claims_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

    def append_job(self, job: Any) -> None:
        if is_dataclass(job):
            self.append(asdict(job))
            return
        self.append(dict(job))

    def iter_records(self) -> Iterable[Dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def iter_claimed_ids(self) -> Set[str]:
        if not self.claims_path.exists():
            return set()
        claimed: Set[str] = set()
        with self.claims_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                request_id = payload.get("request_id")
                if isinstance(request_id, str):
                    claimed.add(request_id)
        return claimed

    def iter_unclaimed(self) -> Iterable[Dict[str, Any]]:
        claimed = self.iter_claimed_ids()
        for row in self.iter_records():
            request_id = row.get("request_id")
            if isinstance(request_id, str) and request_id not in claimed:
                yield row

    def claim_next(self) -> Optional[Dict[str, Any]]:
        for row in self.iter_unclaimed():
            request_id = row.get("request_id")
            if not isinstance(request_id, str):
                continue
            with self.claims_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"request_id": request_id}, sort_keys=True))
                handle.write("\n")
            return row
        return None

    def total_count(self) -> int:
        return sum(1 for _ in self.iter_records())

    def claimed_count(self) -> int:
        return len(self.iter_claimed_ids())

    def unclaimed_count(self) -> int:
        return sum(1 for _ in self.iter_unclaimed())
