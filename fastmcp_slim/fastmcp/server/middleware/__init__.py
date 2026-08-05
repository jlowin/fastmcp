from typing import TYPE_CHECKING

from .authorization import AuthMiddleware
from .middleware import (
    CallNext,
    Middleware,
    MiddlewareContext,
)
from .ping import PingMiddleware

if TYPE_CHECKING:
    from .proxy import (
        ProxyNegotiationMetadataMiddleware as ProxyNegotiationMetadataMiddleware,
    )

__all__ = [
    "AuthMiddleware",
    "CallNext",
    "Middleware",
    "MiddlewareContext",
    "PingMiddleware",
    "ProxyNegotiationMetadataMiddleware",
]


def __getattr__(name: str) -> object:
    if name == "ProxyNegotiationMetadataMiddleware":
        from .proxy import ProxyNegotiationMetadataMiddleware

        return ProxyNegotiationMetadataMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
