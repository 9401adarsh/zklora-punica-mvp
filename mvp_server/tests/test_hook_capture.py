import pytest

torch = pytest.importorskip("torch")
nn = pytest.importorskip("torch.nn")

from mvp_server.runtime.hook_capture import HookCapture


def test_hook_capture_records_shapes() -> None:
    layer = nn.Linear(4, 2, bias=False)
    capture = HookCapture(module_id="layer")
    capture.attach(layer)
    x = torch.randn(3, 4)
    _ = layer(x)
    packet = capture.pop_capture()
    assert packet.x_pre.shape == (3, 4)
    assert packet.delta_post.shape == (3, 2)
    capture.detach()


def test_hook_capture_fallback_when_tensor_numpy_unavailable(monkeypatch) -> None:
    original_numpy = torch.Tensor.numpy

    def _raise_numpy(_self):
        raise RuntimeError("Numpy is not available")

    monkeypatch.setattr(torch.Tensor, "numpy", _raise_numpy, raising=True)
    layer = nn.Linear(4, 2, bias=False)
    capture = HookCapture(module_id="layer")
    capture.attach(layer)
    x = torch.randn(3, 4)
    _ = layer(x)
    packet = capture.pop_capture()
    assert packet.x_pre.shape == (3, 4)
    assert packet.delta_post.shape == (3, 2)
    capture.detach()
    monkeypatch.setattr(torch.Tensor, "numpy", original_numpy, raising=True)
