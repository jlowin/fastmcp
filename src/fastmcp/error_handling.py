"""HTTP error handling utilities for FastMCP tools.

This module provides an optional decorator for converting httpx exceptions
into user-friendly ToolError messages. This is a utility for users who want
more granular control over HTTP error handling beyond what FastMCP's core
error masking provides.

Note: FastMCP's core error handling already handles actionable errors like
rate limiting (429) and timeouts automatically. This decorator is useful when
you want to customize error messages for specific HTTP status codes or when
you want all HTTP errors (not just actionable ones) to have friendly messages.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

import httpx
from typing_extensions import ParamSpec

from fastmcp.exceptions import ToolError

__all__ = ["handle_http_errors"]

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def _handle_httpx_status_error(error: httpx.HTTPStatusError) -> ToolError:
    """Convert httpx HTTPStatusError to ToolError with appropriate message.

    Maps HTTP status codes to user-friendly error messages:
    - 401: "Authentication failed or missing credentials"
    - 403: "Access denied - insufficient permissions"
    - 404: "Resource not found"
    - 429: "Rate limit exceeded, please retry later"
    - 5xx: "Server error, please try again later"
    - Other: "HTTP error {status_code}"

    Args:
        error: The HTTPStatusError to convert.

    Returns:
        ToolError with appropriate user-friendly message.
    """
    status_code = error.response.status_code

    if status_code == 401:
        message = "Authentication failed or missing credentials"
    elif status_code == 403:
        message = "Access denied - insufficient permissions"
    elif status_code == 404:
        message = "Resource not found"
    elif status_code == 429:
        message = "Rate limit exceeded, please retry later"
    elif status_code >= 500:
        message = "Server error, please try again later"
    else:
        message = f"HTTP error {status_code}"

    return ToolError(message)


def _handle_exception(error: Exception, mask_errors: bool) -> ToolError:
    """Convert any exception to ToolError with appropriate message.

    Handles httpx-specific exceptions with user-friendly messages, and
    generic exceptions with optional masking of internal error details.

    Args:
        error: The exception to convert.
        mask_errors: If True, mask internal exception details.

    Returns:
        ToolError with appropriate message based on exception type.
    """
    # Handle httpx-specific exceptions
    if isinstance(error, httpx.HTTPStatusError):
        return _handle_httpx_status_error(error)

    if isinstance(error, httpx.TimeoutException):
        return ToolError("Request timed out, please try again")

    if isinstance(error, httpx.RequestError):
        return ToolError("Network connection error")

    # Generic exception handling
    if mask_errors:
        return ToolError("An unexpected error occurred")
    else:
        return ToolError(f"An unexpected error occurred: {error}")


def handle_http_errors(
    mask_errors: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that converts httpx exceptions into user-friendly ToolError.

    This is an optional utility decorator for users who want more granular
    control over HTTP error handling. FastMCP's core error handling already
    handles actionable errors (429 rate limits, timeouts) automatically.

    Use this decorator when you want:
    - All HTTP errors to have friendly messages (not just actionable ones)
    - Custom error message formatting
    - To bypass FastMCP's default error masking for HTTP errors

    Args:
        mask_errors: If True (default), generic exceptions show a safe message
            without internal details. If False, exception details are included.
            httpx-specific exceptions always show user-friendly messages
            regardless of this setting.

    Returns:
        A decorator that wraps the function with HTTP error handling.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.error_handling import handle_http_errors
        import httpx

        mcp = FastMCP("MyServer")

        @mcp.tool
        @handle_http_errors()
        async def get_user(username: str) -> dict:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.github.com/users/{username}"
                )
                response.raise_for_status()
                return response.json()
        ```

    Built-in error mappings:
        - httpx.HTTPStatusError (401): "Authentication failed or missing credentials"
        - httpx.HTTPStatusError (403): "Access denied - insufficient permissions"
        - httpx.HTTPStatusError (404): "Resource not found"
        - httpx.HTTPStatusError (429): "Rate limit exceeded, please retry later"
        - httpx.HTTPStatusError (5xx): "Server error, please try again later"
        - httpx.HTTPStatusError (other): "HTTP error {status_code}"
        - httpx.TimeoutException: "Request timed out, please try again"
        - httpx.RequestError: "Network connection error"
        - Generic Exception: "An unexpected error occurred" (when masked)
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            # Async wrapper
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    result = await cast(Coroutine[Any, Any, R], func(*args, **kwargs))
                    return result
                except ToolError:
                    # Re-raise ToolError as-is (user explicitly raised it)
                    raise
                except asyncio.CancelledError:
                    # Let cancellations propagate (e.g., on client disconnect)
                    raise
                except Exception as e:
                    func_name = getattr(func, "__name__", repr(func))
                    logger.exception("HTTP error in %r", func_name)
                    raise _handle_exception(e, mask_errors) from e

            return cast(Callable[P, R], async_wrapper)
        else:
            # Sync wrapper
            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    return func(*args, **kwargs)
                except ToolError:
                    # Re-raise ToolError as-is (user explicitly raised it)
                    raise
                except Exception as e:
                    func_name = getattr(func, "__name__", repr(func))
                    logger.exception("HTTP error in %r", func_name)
                    raise _handle_exception(e, mask_errors) from e

            return sync_wrapper

    return decorator
