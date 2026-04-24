from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

import numpy as np

from .hashing import canonicalize_tensor


@dataclass
class CapturePacket:
    module_id: str
    x_pre: np.ndarray
    delta_post: np.ndarray


def _unwrap_first_tensor(value: Any) -> Any:
    if isinstance(value, tuple):
        if not value:
            raise ValueError("hook payload tuple was empty")
        return value[0]
    return value


def _to_numpy(value: Any) -> np.ndarray:
    value = _unwrap_first_tensor(value)
    if hasattr(value, "detach"):  # torch.Tensor
        tensor = value.detach().cpu()
        try:
            value = tensor.numpy()
        except RuntimeError as exc:
            # Some Torch/Numpy version combinations disable tensor.numpy().
            if "Numpy is not available" not in str(exc):
                raise
            value = tensor.tolist()
    return canonicalize_tensor(value)


class HookCapture:
    """Captures pre and post tensors for a target module."""

    def __init__(self, module_id: str) -> None:
        self.module_id = module_id
        self._x_pre: Optional[np.ndarray] = None
        self._delta_post: Optional[np.ndarray] = None
        self._pre_handle = None
        self._post_handle = None

    def attach(self, module: Any) -> None:
        self._pre_handle = module.register_forward_pre_hook(self._pre_hook)
        self._post_handle = module.register_forward_hook(self._post_hook)

    def detach(self) -> None:
        if self._pre_handle is not None:
            self._pre_handle.remove()
            self._pre_handle = None
        if self._post_handle is not None:
            self._post_handle.remove()
            self._post_handle = None

    def _pre_hook(self, _module: Any, args: Tuple[Any, ...]) -> None:
        self._x_pre = _to_numpy(args)

    def _post_hook(self, _module: Any, _args: Tuple[Any, ...], output: Any) -> None:
        self._delta_post = _to_numpy(output)

    def pop_capture(self) -> CapturePacket:
        if self._x_pre is None or self._delta_post is None:
            raise RuntimeError("hook capture is incomplete for current request")
        packet = CapturePacket(
            module_id=self.module_id,
            x_pre=self._x_pre,
            delta_post=self._delta_post,
        )
        self._x_pre = None
        self._delta_post = None
        return packet
