import pytest

from mvp_server.runtime.model_runtime import resolve_module_path


class Leaf:
    def __init__(self, value: int) -> None:
        self.value = value


class Node:
    def __init__(self) -> None:
        self.child = [Leaf(10), Leaf(20)]


def test_resolve_module_path_with_index() -> None:
    root = Node()
    leaf = resolve_module_path(root, "child.1")
    assert leaf.value == 20


def test_resolve_module_path_missing_attribute() -> None:
    root = Node()
    with pytest.raises(ValueError, match="missing attribute"):
        resolve_module_path(root, "missing.0")

