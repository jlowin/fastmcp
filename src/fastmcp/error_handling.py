"""Error handling utilities for FastMCP tools.

This module provides decorators for standardized error handling in MCP tools,
reducing boilerplate and ensuring consistent error messages.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import TypeVar

import httpx
from typing_extensions import ParamSpec

from fastmcp.exceptions import ToolError

__all__ = ["handle_tool_errors"]

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def _format_message(api_name: str | None, message: str) -> str:
    """Format error message with optional API name prefix."""
    if api_name:
        return f"{api_name}: {message}"
    return message


def _handle_httpx_status_error(
    error: httpx.HTTPStatusError, api_name: str | None
) -> ToolError:
    """Convert httpx HTTPStatusError to ToolError with appropriate message."""
    status_code = error.response.status_code

    if status_code == 404:
        message = "Resource not found"
    elif status_code == 429:
        message = "Rate limit exceeded. Please retry later."
    elif status_code >= 500:
        message = "Server error. Please try again later."
    else:
        message = f"HTTP error {status_code}"

    return ToolError(_format_message(api_name, message))


def _handle_exception(
    error: Exception,
    api_name: str | None,
    func_name: str,
    mask_internal_errors: bool,
) -> ToolError:
    """Convert any exception to ToolError with appropriate message."""
    # Handle httpx-specific exceptions
    if isinstance(error, httpx.HTTPStatusError):
        return _handle_httpx_status_error(error, api_name)

    if isinstance(error, httpx.TimeoutException):
        message = "Request timed out. Please try again."
        return ToolError(_format_message(api_name, message))

    if isinstance(error, httpx.RequestError):
        message = "Network connection error."
        return ToolError(_format_message(api_name, message))

    # Generic exception handling
    if mask_internal_errors:
        message = "An unexpected error occurred"
        return ToolError(_format_message(api_name, message))
    else:
        message = f"An unexpected error occurred: {error}"
        return ToolError(_format_message(api_name, message))


def handle_tool_errors(
    api_name: str | None = None,
    *,
    mask_internal_errors: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that converts common HTTP/network exceptions into ToolError.

    This decorator automatically catches exceptions from HTTP client libraries
    (httpx) and converts them into user-friendly ToolError messages. This
    reduces boilerplate error handling code in MCP tools.

    Args:
        api_name: Optional name of the API being called. When provided, this
            name is included as a prefix in error messages (e.g., "GitHub API:
            Resource not found").
        mask_internal_errors: If True (default), generic exceptions show a
            safe message without internal details. If False, exception details
            are included in the message. httpx-specific exceptions always show
            user-friendly messages regardless of this setting.

    Returns:
        A decorator that wraps the function with error handling.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.error_handling import handle_tool_errors
        import httpx

        mcp = FastMCP("MyServer")

        @mcp.tool
        @handle_tool_errors(api_name="GitHub API")
        async def get_user(username: str) -> dict:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.github.com/users/{username}"
                )
                response.raise_for_status()
                return response.json()
        ```

    Built-in error mappings:
        - httpx.HTTPStatusError (404): "Resource not found"
        - httpx.HTTPStatusError (429): "Rate limit exceeded..."
        - httpx.HTTPStatusError (5xx): "Server error..."
        - httpx.HTTPStatusError (other): "HTTP error {status_code}"
        - httpx.TimeoutException: "Request timed out..."
        - httpx.RequestError: "Network connection error."
        - Generic Exception: "An unexpected error occurred" (masked)
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            # Async wrapper
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                try:
                    return await func(*args, **kwargs)
                except ToolError:
                    # Re-raise ToolError as-is (user explicitly raised it)
                    raise
                except Exception as e:
                    func_name = getattr(func, "__name__", repr(func))
                    logger.exception(
                        f"Error in tool {func_name!r} (api_name={api_name!r}): {e}"
                    )
                    raise _handle_exception(
                        e, api_name, func_name, mask_internal_errors
                    ) from e

            return async_wrapper  # type: ignore[return-value]
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
                    logger.exception(
                        f"Error in tool {func_name!r} (api_name={api_name!r}): {e}"
                    )
                    raise _handle_exception(
                        e, api_name, func_name, mask_internal_errors
                    ) from e

            return sync_wrapper  # type: ignore[return-value]

    return decorator
