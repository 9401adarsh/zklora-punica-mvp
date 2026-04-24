from __future__ import annotations

import hashlib


class SamplingPolicy:
    def __init__(self, mode: str, sample_n: int | None = None) -> None:
        self.mode = mode
        self.sample_n = sample_n
        if self.mode not in {"every_request", "sampled"}:
            raise ValueError("invalid sampling mode")
        if self.mode == "sampled" and (self.sample_n is None or self.sample_n < 1):
            raise ValueError("sample_n must be >= 1 for sampled mode")

    def should_sample(self, request_id: str, module_id: str) -> bool:
        if self.mode == "every_request":
            return True
        digest = hashlib.sha256(f"{request_id}:{module_id}".encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return bucket % int(self.sample_n) == 0

