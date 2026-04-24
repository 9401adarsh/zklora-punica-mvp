from __future__ import annotations

from queue import Queue
from typing import Any


class ProofQueue:
    """Bounded queue for proof jobs (used from phase 2 onward)."""

    def __init__(self, maxsize: int = 1024) -> None:
        self._queue: Queue[Any] = Queue(maxsize=maxsize)

    def put(self, item: Any) -> None:
        self._queue.put(item)

    def get(self) -> Any:
        return self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()

