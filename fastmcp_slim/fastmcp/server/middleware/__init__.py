from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from .authorization import AuthMiddleware as AuthMiddleware
    from .middleware import CallNext as CallNext
    from .middleware import Middleware as Middleware
    from .middleware import MiddlewareContext as MiddlewareContext
    from .ping import PingMiddleware as PingMiddleware

__all__ = [
    "AuthMiddleware",
    "CallNext",
    "Middleware",
    "MiddlewareContext",
    "PingMiddleware",
]

_LAZY_IMPORTS = {
    "AuthMiddleware": (".authorization", "AuthMiddleware"),
    "CallNext": (".middleware", "CallNext"),
    "Middleware": (".middleware", "Middleware"),
    "MiddlewareContext": (".middleware", "MiddlewareContext"),
    "PingMiddleware": (".ping", "PingMiddleware"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
