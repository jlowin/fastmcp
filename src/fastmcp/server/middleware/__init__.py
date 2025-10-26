from .middleware import (
    Middleware,
    MiddlewareContext,
    CallNext,
)


def __getattr__(name: str):
    if name == "BulkToolCallerMiddleware":
        from .bulk_tool_caller import BulkToolCallerMiddleware

        return BulkToolCallerMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BulkToolCallerMiddleware",
    "CallNext",
    "Middleware",
    "MiddlewareContext",
]
