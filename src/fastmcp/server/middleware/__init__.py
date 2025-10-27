from typing import TYPE_CHECKING

from .middleware import (
    Middleware,
    MiddlewareContext,
    CallNext,
)

if TYPE_CHECKING:
    from .bulk_tool_caller import BulkToolCallerMiddleware


def __getattr__(name: str):
    if name == "BulkToolCallerMiddleware":
        from .bulk_tool_caller import BulkToolCallerMiddleware

        return BulkToolCallerMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Ensure BulkToolCallerMiddleware shows up in dir() output."""
    return sorted([*globals().keys(), "BulkToolCallerMiddleware"])


__all__ = [
    "BulkToolCallerMiddleware",
    "CallNext",
    "Middleware",
    "MiddlewareContext",
]
