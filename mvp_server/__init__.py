"""MVP proof-aware inference server package."""

from .config import AppConfig

__all__ = ["AppConfig", "MVPServer"]


def __getattr__(name: str):
    if name == "MVPServer":
        from .api.server import MVPServer

        return MVPServer
    raise AttributeError(name)
