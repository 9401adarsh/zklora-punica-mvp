from __future__ import annotations

from queue import Full, Queue
from typing import Any


class WitnessQueue:
    """Phase 2 queue placeholder; non-blocking enqueue semantics are fixed here."""

    def __init__(self, maxsize: int = 1024) -> None:
        self._queue: Queue[Any] = Queue(maxsize=maxsize)
        self.overflow_count = 0

    def put_nowait(self, item: Any) -> bool:
        try:
            self._queue.put_nowait(item)
            return True
        except Full:
            self.overflow_count += 1
            return False

    def get(self) -> Any:
        return self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()

