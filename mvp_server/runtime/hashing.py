from __future__ import annotations

import hashlib
import json
from typing import Any, Tuple

import numpy as np


def canonicalize_tensor(value: Any) -> np.ndarray:
    """Normalizes tensors/arrays for deterministic hashing."""
    if isinstance(value, np.ndarray):
        array = value
    else:
        array = np.asarray(value)
    array = np.asarray(array, dtype=np.float32)
    return np.ascontiguousarray(array)


def canonical_header(array: np.ndarray, schema_version: int) -> bytes:
    payload = {
        "hash_schema_version": int(schema_version),
        "dtype": str(array.dtype),
        "shape": list(array.shape),
        "layout": "c_contiguous",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_tensor(value: Any, schema_version: int = 1) -> Tuple[str, np.ndarray]:
    """Returns hash digest and canonicalized array."""
    array = canonicalize_tensor(value)
    hasher = hashlib.sha256()
    hasher.update(canonical_header(array, schema_version))
    hasher.update(array.tobytes(order="C"))
    return hasher.hexdigest(), array

