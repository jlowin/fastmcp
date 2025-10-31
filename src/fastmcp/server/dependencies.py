from __future__ import annotations

import contextlib
import inspect
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from functools import lru_cache
from typing import TYPE_CHECKING, Any, get_type_hints

from docket.dependencies import _Depends, get_dependency_parameters
from mcp.server.auth.middleware.auth_context import (
    get_access_token as _sdk_get_access_token,
)
from mcp.server.auth.provider import (
    AccessToken as _SDKAccessToken,
)
from starlette.requests import Request

from fastmcp.server.auth import AccessToken
from fastmcp.utilities.types import is_class_member_of_type

if TYPE_CHECKING:
    from fastmcp.server.context import Context

__all__ = [
    "AccessToken",
    "get_access_token",
    "get_context",
    "get_http_headers",
    "get_http_request",
    "resolve_dependencies",
    "without_injected_parameters",
]


def _find_kwarg_by_type(fn: Callable, kwarg_type: type) -> str | None:
    """Find the name of the kwarg that is of type kwarg_type.

    This is the legacy dependency injection approach, used specifically for
    injecting the Context object when a function parameter is typed as Context.

    Includes union types that contain the kwarg_type, as well as Annotated types.
    """

    if inspect.ismethod(fn) and hasattr(fn, "__func__"):
        fn = fn.__func__

    try:
        type_hints = get_type_hints(fn, include_extras=True)
    except Exception:
        type_hints = getattr(fn, "__annotations__", {})

    sig = inspect.signature(fn)
    for name, param in sig.parameters.items():
        annotation = type_hints.get(name, param.annotation)
        if is_class_member_of_type(annotation, kwarg_type):
            return name
    return None


@lru_cache(maxsize=5000)
def without_injected_parameters(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a wrapper function without injected parameters.

    Returns a wrapper that excludes Context and Docket dependency parameters,
    making it safe to use with Pydantic TypeAdapter for schema generation and
    validation. The wrapper internally handles all dependency resolution and
    Context injection when called.

    Args:
        fn: Original function with Context and/or dependencies

    Returns:
        Async wrapper function without injected parameters
    """
    from fastmcp.server.context import Context

    # Identify parameters to exclude
    context_kwarg = _find_kwarg_by_type(fn, Context)
    dependency_params = get_dependency_parameters(fn)

    exclude = set()
    if context_kwarg:
        exclude.add(context_kwarg)
    if dependency_params:
        exclude.update(dependency_params.keys())

    if not exclude:
        return fn

    # Build new signature with only user parameters
    sig = inspect.signature(fn)
    user_params = [
        param for name, param in sig.parameters.items() if name not in exclude
    ]
    new_sig = inspect.Signature(user_params)

    # Create async wrapper that handles dependency resolution
    async def wrapper(**user_kwargs: Any) -> Any:
        async with resolve_dependencies(fn, user_kwargs) as resolved_kwargs:
            result = fn(**resolved_kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

    # Set wrapper metadata (only parameter annotations, not return type)
    wrapper.__signature__ = new_sig  # type: ignore
    wrapper.__annotations__ = {
        k: v
        for k, v in getattr(fn, "__annotations__", {}).items()
        if k not in exclude and k != "return"
    }
    wrapper.__name__ = getattr(fn, "__name__", "wrapper")
    wrapper.__doc__ = getattr(fn, "__doc__", None)

    return wrapper


@asynccontextmanager
async def _resolve_fastmcp_dependencies(
    fn: Callable[..., Any], arguments: dict[str, Any]
) -> AsyncGenerator[dict[str, Any], None]:
    """Resolve Docket dependencies for a FastMCP function.

    Sets up the minimal context needed for Docket's Depends() to work:
    - A cache for resolved dependencies
    - An AsyncExitStack for managing context manager lifetimes

    Note: This does NOT set up Docket's Execution context. If user code needs
    Docket-specific dependencies like TaskArgument(), TaskKey(), etc., those
    will fail with clear errors about missing context.

    Args:
        fn: The function to resolve dependencies for
        arguments: The arguments passed to the function

    Yields:
        Dictionary of resolved dependencies merged with provided arguments
    """
    dependency_params = get_dependency_parameters(fn)

    if not dependency_params:
        yield arguments
        return

    # Initialize dependency cache and exit stack
    cache_token = _Depends.cache.set({})
    try:
        async with AsyncExitStack() as stack:
            stack_token = _Depends.stack.set(stack)
            try:
                resolved: dict[str, Any] = {}

                for parameter, dependency in dependency_params.items():
                    # If argument was explicitly provided, use that instead
                    if parameter in arguments:
                        resolved[parameter] = arguments[parameter]
                        continue

                    # Resolve the dependency
                    try:
                        resolved[parameter] = await stack.enter_async_context(
                            dependency
                        )
                    except Exception as error:
                        fn_name = getattr(fn, "__name__", repr(fn))
                        raise RuntimeError(
                            f"Failed to resolve dependency '{parameter}' for {fn_name}"
                        ) from error

                # Merge resolved dependencies with provided arguments
                final_arguments = {**arguments, **resolved}

                yield final_arguments
            finally:
                _Depends.stack.reset(stack_token)
    finally:
        _Depends.cache.reset(cache_token)


@asynccontextmanager
async def resolve_dependencies(
    fn: Callable[..., Any], arguments: dict[str, Any]
) -> AsyncGenerator[dict[str, Any], None]:
    """Resolve dependencies and inject Context for a FastMCP function.

    User arguments are already validated before this is called (either by the
    wrapper function's TypeAdapter, or for resources/prompts by their own logic).

    This function just:
    1. Resolves Docket dependencies (if any)
    2. Injects Context (if needed)
    3. Merges everything together

    Args:
        fn: The function to resolve dependencies for
        arguments: The validated user arguments

    Yields:
        Dictionary of user args + resolved dependencies + Context

    Example:
        ```python
        async with resolve_dependencies(my_tool, {"name": "Alice"}) as kwargs:
            result = my_tool(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        ```
    """
    from fastmcp.server.context import Context

    async with _resolve_fastmcp_dependencies(fn, arguments) as resolved_kwargs:
        # Inject Context if needed
        context_kwarg = _find_kwarg_by_type(fn, kwarg_type=Context)
        if context_kwarg and context_kwarg not in resolved_kwargs:
            resolved_kwargs[context_kwarg] = get_context()

        yield resolved_kwargs


def get_context() -> Context:
    from fastmcp.server.context import _current_context

    context = _current_context.get()
    if context is None:
        raise RuntimeError("No active context found.")
    return context


def get_http_request() -> Request:
    from mcp.server.lowlevel.server import request_ctx

    request = None
    with contextlib.suppress(LookupError):
        request = request_ctx.get().request

    if request is None:
        raise RuntimeError("No active HTTP request found.")
    return request


def get_http_headers(include_all: bool = False) -> dict[str, str]:
    """
    Extract headers from the current HTTP request if available.

    Never raises an exception, even if there is no active HTTP request (in which case
    an empty dict is returned).

    By default, strips problematic headers like `content-length` that cause issues if forwarded to downstream clients.
    If `include_all` is True, all headers are returned.
    """
    if include_all:
        exclude_headers = set()
    else:
        exclude_headers = {
            "host",
            "content-length",
            "connection",
            "transfer-encoding",
            "upgrade",
            "te",
            "keep-alive",
            "expect",
            "accept",
            # Proxy-related headers
            "proxy-authenticate",
            "proxy-authorization",
            "proxy-connection",
            # MCP-related headers
            "mcp-session-id",
        }
        # (just in case)
        if not all(h.lower() == h for h in exclude_headers):
            raise ValueError("Excluded headers must be lowercase")
    headers = {}

    try:
        request = get_http_request()
        for name, value in request.headers.items():
            lower_name = name.lower()
            if lower_name not in exclude_headers:
                headers[lower_name] = str(value)
        return headers
    except RuntimeError:
        return {}


def get_access_token() -> AccessToken | None:
    """
    Get the FastMCP access token from the current context.

    Returns:
        The access token if an authenticated user is available, None otherwise.
    """
    #
    access_token: _SDKAccessToken | None = _sdk_get_access_token()

    if access_token is None or isinstance(access_token, AccessToken):
        return access_token

    # If the object is not a FastMCP AccessToken, convert it to one if the fields are compatible
    # This is a workaround for the case where the SDK returns a different type
    # If it fails, it will raise a TypeError
    try:
        access_token_as_dict = access_token.model_dump()
        return AccessToken(
            token=access_token_as_dict["token"],
            client_id=access_token_as_dict["client_id"],
            scopes=access_token_as_dict["scopes"],
            # Optional fields
            expires_at=access_token_as_dict.get("expires_at"),
            resource_owner=access_token_as_dict.get("resource_owner"),
            claims=access_token_as_dict.get("claims"),
        )
    except Exception as e:
        raise TypeError(
            f"Expected fastmcp.server.auth.auth.AccessToken, got {type(access_token).__name__}. "
            "Ensure the SDK is using the correct AccessToken type."
        ) from e
