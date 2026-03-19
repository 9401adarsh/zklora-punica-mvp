import numpy as np

from mvp_server.runtime.hashing import hash_tensor


def test_hash_tensor_deterministic() -> None:
    value = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    h1, arr1 = hash_tensor(value, schema_version=1)
    h2, arr2 = hash_tensor(value.astype(np.float32), schema_version=1)
    assert h1 == h2
    assert arr1.dtype == np.float32
    assert arr2.dtype == np.float32


def test_hash_tensor_changes_with_data() -> None:
    h1, _ = hash_tensor(np.array([1, 2, 3], dtype=np.float32), schema_version=1)
    h2, _ = hash_tensor(np.array([1, 2, 4], dtype=np.float32), schema_version=1)
    assert h1 != h2

