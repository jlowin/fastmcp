"""Dependency injection for FastMCP.

DI features (Depends, CurrentContext, CurrentFastMCP) work without pydocket
using a vendored DI engine. Only task-related dependencies (CurrentDocket,
CurrentWorker) and background task execution require fastmcp[tasks].
"""

from __future__ import annotations

import contextlib
import inspect
import weakref
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Protocol, cast, get_type_hints, runtime_checkable

from mcp.server.auth.middleware.auth_context import (
    get_access_token as _sdk_get_access_token,
)
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import (
    AccessToken as _SDKAccessToken,
)
from mcp.server.lowlevel.server import request_ctx
from starlette.requests import Request

from fastmcp.exceptions import FastMCPError
from fastmcp.server.auth import AccessToken
from fastmcp.server.http import _current_http_request
from fastmcp.utilities.async_utils import call_sync_fn_in_threadpool
from fastmcp.utilities.types import find_kwarg_by_type, is_class_member_of_type

if TYPE_CHECKING:
    from docket import Docket
    from docket.worker import Worker
    from mcp.server.session import ServerSession

    from fastmcp.server.context import Context
    from fastmcp.server.server import FastMCP


__all__ = [
    "AccessToken",
    "CurrentContext",
    "CurrentDocket",
    "CurrentFastMCP",
    "CurrentTaskContext",
    "CurrentWorker",
    "Progress",
    "TaskContext",
    "TaskContextInfo",
    "get_access_token",
    "get_context",
    "get_http_headers",
    "get_http_request",
    "get_server",
    "get_task_context",
    "get_task_session",
    "is_docket_available",
    "register_task_session",
    "require_docket",
    "resolve_dependencies",
    "transform_context_annotations",
    "without_injected_parameters",
]


# --- TaskContextInfo and get_task_context ---


@dataclass(frozen=True, slots=True)
class TaskContextInfo:
    """Information about the current background task context.

    Returned by ``get_task_context()`` when running inside a Docket worker.
    Contains identifiers needed to communicate with the MCP session.
    """

    task_id: str
    """The MCP task ID (server-generated UUID)."""

    session_id: str
    """The session ID that submitted this task."""


def get_task_context() -> TaskContextInfo | None:
    """Get the current task context if running inside a background task worker.

    This function extracts task information from the Docket execution context.
    Returns None if not running in a task context (e.g., foreground execution).

    Returns:
        TaskContextInfo with task_id and session_id, or None if not in a task.
    """
    if not is_docket_available():
        return None

    from docket.dependencies import Dependency as DocketDependency

    try:
        execution = DocketDependency.execution.get()
        # Parse the task key: {session_id}:{task_id}:{task_type}:{component}
        from fastmcp.server.tasks.keys import parse_task_key

        key_parts = parse_task_key(execution.key)
        return TaskContextInfo(
            task_id=key_parts["client_task_id"],
            session_id=key_parts["session_id"],
        )
    except LookupError:
        # Not in worker context
        return None
    except (ValueError, KeyError):
        # Invalid task key format
        return None


# --- Session registry for TaskContext ---


_task_sessions: dict[str, weakref.ref[ServerSession]] = {}


def register_task_session(session_id: str, session: ServerSession) -> None:
    """Register a session for TaskContext access in background tasks.

    Called automatically when a task is submitted to Docket. The session is
    stored as a weakref so it doesn't prevent garbage collection when the
    client disconnects.

    Args:
        session_id: The session identifier
        session: The ServerSession instance
    """
    _task_sessions[session_id] = weakref.ref(session)


def get_task_session(session_id: str) -> ServerSession | None:
    """Get a registered session by ID if still alive.

    Args:
        session_id: The session identifier

    Returns:
        The ServerSession if found and alive, None otherwise
    """
    ref = _task_sessions.get(session_id)
    if ref is None:
        return None
    session = ref()
    if session is None:
        # Session was garbage collected, clean up entry
        _task_sessions.pop(session_id, None)
    return session


# --- ContextVars ---

_current_server: ContextVar[weakref.ref[FastMCP] | None] = ContextVar(
    "server", default=None
)
_current_docket: ContextVar[Docket | None] = ContextVar("docket", default=None)
_current_worker: ContextVar[Worker | None] = ContextVar("worker", default=None)


# --- Docket availability check ---

_DOCKET_AVAILABLE: bool | None = None


def is_docket_available() -> bool:
    """Check if pydocket is installed."""
    global _DOCKET_AVAILABLE
    if _DOCKET_AVAILABLE is None:
        try:
            import docket  # noqa: F401

            _DOCKET_AVAILABLE = True
        except ImportError:
            _DOCKET_AVAILABLE = False
    return _DOCKET_AVAILABLE


def require_docket(feature: str) -> None:
    """Raise ImportError with install instructions if docket not available.

    Args:
        feature: Description of what requires docket (e.g., "`task=True`",
                 "CurrentDocket()"). Will be included in the error message.
    """
    if not is_docket_available():
        raise ImportError(
            f"FastMCP background tasks require the `tasks` extra. "
            f"Install with: pip install 'fastmcp[tasks]'. "
            f"(Triggered by {feature})"
        )


# --- Dependency injection imports ---
# Try docket first for isinstance compatibility in worker context,
# fall back to vendored DI engine when docket is not installed.

try:
    from docket.dependencies import (
        Dependency,
        _Depends,
        get_dependency_parameters,
    )
except ImportError:
    from fastmcp._vendor.docket_di import (
        Dependency,
        _Depends,
        get_dependency_parameters,
    )

# Import Progress separately to avoid breaking DI fallback if Progress is missing
try:
    from docket.dependencies import Progress as DocketProgress
except ImportError:
    DocketProgress = None  # type: ignore[assignment]


# --- Context utilities ---


def transform_context_annotations(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Transform ctx: Context into ctx: Context = CurrentContext().

    Transforms ALL params typed as Context to use Docket's DI system,
    unless they already have a Dependency-based default (like CurrentContext()).

    This unifies the legacy type annotation DI with Docket's Depends() system,
    allowing both patterns to work through a single resolution path.

    Note: Only POSITIONAL_OR_KEYWORD parameters are reordered (params with defaults
    after those without). KEYWORD_ONLY parameters keep their position since Python
    allows them to have defaults in any order.

    Args:
        fn: Function to transform

    Returns:
        Function with modified signature (same function object, updated __signature__)
    """
    from fastmcp.server.context import Context

    # Get the function's signature
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return fn

    # Get type hints for accurate type checking
    try:
        type_hints = get_type_hints(fn, include_extras=True)
    except Exception:
        type_hints = getattr(fn, "__annotations__", {})

    # First pass: identify which params need transformation
    params_to_transform: set[str] = set()
    for name, param in sig.parameters.items():
        annotation = type_hints.get(name, param.annotation)
        if is_class_member_of_type(annotation, Context):
            if not isinstance(param.default, Dependency):
                params_to_transform.add(name)

    if not params_to_transform:
        return fn

    # Second pass: build new param list preserving parameter kind structure
    # Python signature structure: [POSITIONAL_ONLY] / [POSITIONAL_OR_KEYWORD] *args [KEYWORD_ONLY] **kwargs
    # Within POSITIONAL_ONLY and POSITIONAL_OR_KEYWORD: params without defaults must come first
    # KEYWORD_ONLY params can have defaults in any order
    P = inspect.Parameter

    # Group params by section, preserving order within each
    positional_only_no_default: list[P] = []
    positional_only_with_default: list[P] = []
    positional_or_keyword_no_default: list[P] = []
    positional_or_keyword_with_default: list[P] = []
    var_positional: list[P] = []  # *args (at most one)
    keyword_only: list[P] = []  # After * or *args, order preserved
    var_keyword: list[P] = []  # **kwargs (at most one)

    for name, param in sig.parameters.items():
        # Transform Context params by adding CurrentContext default
        if name in params_to_transform:
            # We use CurrentContext() instead of Depends(get_context) because
            # get_context() returns the Context which is an AsyncContextManager,
            # and the DI system would try to enter it again (it's already entered)
            param = param.replace(default=CurrentContext())

        # Sort into buckets based on parameter kind
        if param.kind == P.POSITIONAL_ONLY:
            if param.default is P.empty:
                positional_only_no_default.append(param)
            else:
                positional_only_with_default.append(param)
        elif param.kind == P.POSITIONAL_OR_KEYWORD:
            if param.default is P.empty:
                positional_or_keyword_no_default.append(param)
            else:
                positional_or_keyword_with_default.append(param)
        elif param.kind == P.VAR_POSITIONAL:
            var_positional.append(param)
        elif param.kind == P.KEYWORD_ONLY:
            keyword_only.append(param)
        elif param.kind == P.VAR_KEYWORD:
            var_keyword.append(param)

    # Reconstruct parameter list maintaining Python's required structure
    new_params: list[P] = (
        positional_only_no_default
        + positional_only_with_default
        + positional_or_keyword_no_default
        + positional_or_keyword_with_default
        + var_positional
        + keyword_only
        + var_keyword
    )

    # Update function's signature in place
    # Handle methods by setting signature on the underlying function
    # For bound methods, we need to preserve the 'self' parameter because
    # inspect.signature(bound_method) automatically removes the first param
    if inspect.ismethod(fn):
        # Get the original __func__ signature which includes 'self'
        func_sig = inspect.signature(fn.__func__)
        # Insert 'self' at the beginning of our new params
        self_param = next(iter(func_sig.parameters.values()))  # Should be 'self'
        new_sig = func_sig.replace(parameters=[self_param, *new_params])
        fn.__func__.__signature__ = new_sig  # type: ignore[union-attr]
    else:
        new_sig = sig.replace(parameters=new_params)
        fn.__signature__ = new_sig  # type: ignore[attr-defined]

    # Clear caches that may have cached the old signature
    # This ensures get_dependency_parameters and without_injected_parameters
    # see the transformed signature
    _clear_signature_caches(fn)

    return fn


def _clear_signature_caches(fn: Callable[..., Any]) -> None:
    """Clear signature-related caches for a function.

    Called after modifying a function's signature to ensure downstream
    code sees the updated signature.
    """
    # Clear vendored DI caches
    from fastmcp._vendor.docket_di import _parameter_cache, _signature_cache

    _signature_cache.pop(fn, None)
    _parameter_cache.pop(fn, None)

    # Also clear for __func__ if it's a method
    if inspect.ismethod(fn):
        _signature_cache.pop(fn.__func__, None)
        _parameter_cache.pop(fn.__func__, None)

    # Try to clear docket caches if docket is installed
    if is_docket_available():
        try:
            from docket.dependencies import _parameter_cache as docket_param_cache
            from docket.execution import _signature_cache as docket_sig_cache

            docket_sig_cache.pop(fn, None)
            docket_param_cache.pop(fn, None)
            if inspect.ismethod(fn):
                docket_sig_cache.pop(fn.__func__, None)
                docket_param_cache.pop(fn.__func__, None)
        except (ImportError, AttributeError):
            pass  # Cache access not available in this docket version


def get_context() -> Context:
    """Get the current FastMCP Context instance directly."""
    from fastmcp.server.context import _current_context

    context = _current_context.get()
    if context is None:
        raise RuntimeError("No active context found.")
    return context


def get_server() -> FastMCP:
    """Get the current FastMCP server instance directly.

    Returns:
        The active FastMCP server

    Raises:
        RuntimeError: If no server in context
    """
    server_ref = _current_server.get()
    if server_ref is None:
        raise RuntimeError("No FastMCP server instance in context")
    server = server_ref()
    if server is None:
        raise RuntimeError("FastMCP server instance is no longer available")
    return server


def get_http_request() -> Request:
    """Get the current HTTP request.

    Tries MCP SDK's request_ctx first, then falls back to FastMCP's HTTP context.
    """
    # Try MCP SDK's request_ctx first (set during normal MCP request handling)
    request = None
    with contextlib.suppress(LookupError):
        request = request_ctx.get().request

    # Fallback to FastMCP's HTTP context variable
    # This is needed during `on_initialize` middleware where request_ctx isn't set yet
    if request is None:
        request = _current_http_request.get()

    if request is None:
        raise RuntimeError("No active HTTP request found.")
    return request


def get_http_headers(include_all: bool = False) -> dict[str, str]:
    """Extract headers from the current HTTP request if available.

    Never raises an exception, even if there is no active HTTP request (in which case
    an empty dict is returned).

    By default, strips problematic headers like `content-length` that cause issues
    if forwarded to downstream clients. If `include_all` is True, all headers are returned.
    """
    if include_all:
        exclude_headers: set[str] = set()
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
    headers: dict[str, str] = {}

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
    """Get the FastMCP access token from the current context.

    This function first tries to get the token from the current HTTP request's scope,
    which is more reliable for long-lived connections where the SDK's auth_context_var
    may become stale after token refresh. Falls back to the SDK's context var if no
    request is available.

    Returns:
        The access token if an authenticated user is available, None otherwise.
    """
    access_token: _SDKAccessToken | None = None

    # First, try to get from current HTTP request's scope (issue #1863)
    # This is more reliable than auth_context_var for Streamable HTTP sessions
    # where tokens may be refreshed between MCP messages
    try:
        request = get_http_request()
        user = request.scope.get("user")
        if isinstance(user, AuthenticatedUser):
            access_token = user.access_token
    except RuntimeError:
        # No HTTP request available, fall back to context var
        pass

    # Fall back to SDK's context var if we didn't get a token from the request
    if access_token is None:
        access_token = _sdk_get_access_token()

    if access_token is None or isinstance(access_token, AccessToken):
        return access_token

    # If the object is not a FastMCP AccessToken, convert it to one if the
    # fields are compatible (e.g. `claims` is not present in the SDK's AccessToken).
    # This is a workaround for the case where the SDK or auth provider returns a different type
    # If it fails, it will raise a TypeError
    try:
        access_token_as_dict = access_token.model_dump()
        return AccessToken(
            token=access_token_as_dict["token"],
            client_id=access_token_as_dict["client_id"],
            scopes=access_token_as_dict["scopes"],
            # Optional fields
            expires_at=access_token_as_dict.get("expires_at"),
            resource=access_token_as_dict.get("resource"),
            claims=access_token_as_dict.get("claims") or {},
        )
    except Exception as e:
        raise TypeError(
            f"Expected fastmcp.server.auth.auth.AccessToken, got {type(access_token).__name__}. "
            "Ensure the SDK is using the correct AccessToken type."
        ) from e


# --- Schema generation helper ---


@lru_cache(maxsize=5000)
def without_injected_parameters(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Create a wrapper function without injected parameters.

    Returns a wrapper that excludes Context and Docket dependency parameters,
    making it safe to use with Pydantic TypeAdapter for schema generation and
    validation. The wrapper internally handles all dependency resolution and
    Context injection when called.

    Handles:
    - Legacy Context injection (always works)
    - Depends() injection (always works - uses docket or vendored DI engine)

    Args:
        fn: Original function with Context and/or dependencies

    Returns:
        Async wrapper function without injected parameters
    """
    from fastmcp.server.context import Context

    # Identify parameters to exclude
    context_kwarg = find_kwarg_by_type(fn, Context)
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
    fn_is_async = inspect.iscoroutinefunction(fn)

    async def wrapper(**user_kwargs: Any) -> Any:
        async with resolve_dependencies(fn, user_kwargs) as resolved_kwargs:
            if fn_is_async:
                return await fn(**resolved_kwargs)
            else:
                # Run sync functions in threadpool to avoid blocking the event loop
                result = await call_sync_fn_in_threadpool(fn, **resolved_kwargs)
                # Handle sync wrappers that return awaitables (e.g., partial(async_fn))
                if inspect.isawaitable(result):
                    result = await result
                return result

    # Set wrapper metadata (only parameter annotations, not return type)
    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    wrapper.__annotations__ = {
        k: v
        for k, v in getattr(fn, "__annotations__", {}).items()
        if k not in exclude and k != "return"
    }
    wrapper.__name__ = getattr(fn, "__name__", "wrapper")
    wrapper.__doc__ = getattr(fn, "__doc__", None)

    return wrapper


# --- Dependency resolution ---


@asynccontextmanager
async def _resolve_fastmcp_dependencies(
    fn: Callable[..., Any], arguments: dict[str, Any]
) -> AsyncGenerator[dict[str, Any], None]:
    """Resolve Docket dependencies for a FastMCP function.

    Sets up the minimal context needed for Docket's Depends() to work:
    - A cache for resolved dependencies
    - An AsyncExitStack for managing context manager lifetimes

    The Docket instance (for CurrentDocket dependency) is managed separately
    by the server's lifespan and made available via ContextVar.

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
                    except FastMCPError:
                        # Let FastMCPError subclasses (ToolError, ResourceError, etc.)
                        # propagate unchanged so they can be handled appropriately
                        raise
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
    """Resolve dependencies for a FastMCP function.

    This function:
    1. Filters out any dependency parameter names from user arguments (security)
    2. Resolves Depends() parameters via the DI system

    The filtering prevents external callers from overriding injected parameters by
    providing values for dependency parameter names. This is a security feature.

    Note: Context injection is handled via transform_context_annotations() which
    converts `ctx: Context` to `ctx: Context = Depends(get_context)` at registration
    time, so all injection goes through the unified DI system.

    Args:
        fn: The function to resolve dependencies for
        arguments: User arguments (may contain keys that match dependency names,
                  which will be filtered out)

    Yields:
        Dictionary of filtered user args + resolved dependencies

    Example:
        ```python
        async with resolve_dependencies(my_tool, {"name": "Alice"}) as kwargs:
            result = my_tool(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        ```
    """
    # Filter out dependency parameters from user arguments to prevent override
    # This is a security measure - external callers should never be able to
    # provide values for injected parameters
    dependency_params = get_dependency_parameters(fn)
    user_args = {k: v for k, v in arguments.items() if k not in dependency_params}

    async with _resolve_fastmcp_dependencies(fn, user_args) as resolved_kwargs:
        yield resolved_kwargs


# --- Dependency classes ---
# These must inherit from docket.dependencies.Dependency when docket is available
# so that get_dependency_parameters can detect them.


class _CurrentContext(Dependency):  # type: ignore[misc]
    """Async context manager for Context dependency."""

    async def __aenter__(self) -> Context:
        return get_context()

    async def __aexit__(self, *args: object) -> None:
        pass


def CurrentContext() -> Context:
    """Get the current FastMCP Context instance.

    This dependency provides access to the active FastMCP Context for the
    current MCP operation (tool/resource/prompt call).

    Returns:
        A dependency that resolves to the active Context instance

    Raises:
        RuntimeError: If no active context found (during resolution)

    Example:
        ```python
        from fastmcp.dependencies import CurrentContext

        @mcp.tool()
        async def log_progress(ctx: Context = CurrentContext()) -> str:
            ctx.report_progress(50, 100, "Halfway done")
            return "Working"
        ```
    """
    return cast("Context", _CurrentContext())


class _CurrentDocket(Dependency):  # type: ignore[misc]
    """Async context manager for Docket dependency."""

    async def __aenter__(self) -> Docket:
        require_docket("CurrentDocket()")
        docket = _current_docket.get()
        if docket is None:
            raise RuntimeError(
                "No Docket instance found. Docket is only initialized when there are "
                "task-enabled components (task=True). Add task=True to a component "
                "to enable Docket infrastructure."
            )
        return docket

    async def __aexit__(self, *args: object) -> None:
        pass


def CurrentDocket() -> Docket:
    """Get the current Docket instance managed by FastMCP.

    This dependency provides access to the Docket instance that FastMCP
    automatically creates for background task scheduling.

    Returns:
        A dependency that resolves to the active Docket instance

    Raises:
        RuntimeError: If not within a FastMCP server context
        ImportError: If fastmcp[tasks] not installed

    Example:
        ```python
        from fastmcp.dependencies import CurrentDocket

        @mcp.tool()
        async def schedule_task(docket: Docket = CurrentDocket()) -> str:
            await docket.add(some_function)(arg1, arg2)
            return "Scheduled"
        ```
    """
    require_docket("CurrentDocket()")
    return cast("Docket", _CurrentDocket())


class _CurrentWorker(Dependency):  # type: ignore[misc]
    """Async context manager for Worker dependency."""

    async def __aenter__(self) -> Worker:
        require_docket("CurrentWorker()")
        worker = _current_worker.get()
        if worker is None:
            raise RuntimeError(
                "No Worker instance found. Worker is only initialized when there are "
                "task-enabled components (task=True). Add task=True to a component "
                "to enable Docket infrastructure."
            )
        return worker

    async def __aexit__(self, *args: object) -> None:
        pass


def CurrentWorker() -> Worker:
    """Get the current Docket Worker instance managed by FastMCP.

    This dependency provides access to the Worker instance that FastMCP
    automatically creates for background task processing.

    Returns:
        A dependency that resolves to the active Worker instance

    Raises:
        RuntimeError: If not within a FastMCP server context
        ImportError: If fastmcp[tasks] not installed

    Example:
        ```python
        from fastmcp.dependencies import CurrentWorker

        @mcp.tool()
        async def check_worker_status(worker: Worker = CurrentWorker()) -> str:
            return f"Worker: {worker.name}"
        ```
    """
    require_docket("CurrentWorker()")
    return cast("Worker", _CurrentWorker())


class _CurrentFastMCP(Dependency):  # type: ignore[misc]
    """Async context manager for FastMCP server dependency."""

    async def __aenter__(self) -> FastMCP:
        server_ref = _current_server.get()
        if server_ref is None:
            raise RuntimeError("No FastMCP server instance in context")
        server = server_ref()
        if server is None:
            raise RuntimeError("FastMCP server instance is no longer available")
        return server

    async def __aexit__(self, *args: object) -> None:
        pass


def CurrentFastMCP() -> FastMCP:
    """Get the current FastMCP server instance.

    This dependency provides access to the active FastMCP server.

    Returns:
        A dependency that resolves to the active FastMCP server

    Raises:
        RuntimeError: If no server in context (during resolution)

    Example:
        ```python
        from fastmcp.dependencies import CurrentFastMCP

        @mcp.tool()
        async def introspect(server: FastMCP = CurrentFastMCP()) -> str:
            return f"Server: {server.name}"
        ```
    """
    from fastmcp.server.server import FastMCP

    return cast(FastMCP, _CurrentFastMCP())


# --- TaskContext for background task elicitation/sampling ---


class TaskContext:
    """Context for background tasks with elicitation and sampling support.

    TaskContext provides access to elicitation and sampling from within
    background tasks (tools/resources/prompts with ``task=True``). Unlike the
    regular Context, TaskContext IS available in Docket workers.

    When ``elicit()`` or ``sample()`` is called, TaskContext automatically:

    1. Updates task status to ``input_required``
    2. Includes ``related-task`` metadata in the request
    3. Waits for the response
    4. Restores task status to ``working``

    This implements SEP-1686 ``input_required`` semantics.

    Note:
        TaskContext is only available in embedded worker mode (the FastMCP
        default). Distributed workers running in separate processes cannot
        access the session and will raise an error.

    Example:
        .. code-block:: python

            from fastmcp import FastMCP
            from fastmcp.dependencies import CurrentTaskContext, TaskContext

            mcp = FastMCP("my-server")

            @mcp.tool(task=True)
            async def ask_user(task_ctx: TaskContext = CurrentTaskContext()) -> str:
                result = await task_ctx.elicit(
                    message="What is your name?",
                    response_type=str,
                )
                if result.action == "accept":
                    return f"Hello, {result.data}!"
                return "No name provided"
    """

    __slots__ = ("_task_id", "_session_id")

    def __init__(self, task_id: str, session_id: str) -> None:
        self._task_id = task_id
        self._session_id = session_id

    @property
    def task_id(self) -> str:
        """The MCP task ID (server-generated UUID)."""
        return self._task_id

    @property
    def session_id(self) -> str:
        """The session ID for this task."""
        return self._session_id

    def _get_session(self) -> ServerSession:
        """Get the associated ServerSession.

        Raises:
            RuntimeError: If session is no longer available
        """
        session = get_task_session(self._session_id)
        if session is None:
            raise RuntimeError(
                "Session is no longer available. This can happen if the client "
                "disconnected or if running in distributed worker mode (which "
                "doesn't support TaskContext). For distributed workers, consider "
                "using a message queue pattern."
            )
        return session

    def _get_docket(self) -> Docket:
        """Get the current Docket instance.

        Raises:
            RuntimeError: If no Docket instance is available
        """
        docket = _current_docket.get()
        if docket is None:
            raise RuntimeError(
                "No Docket instance available. This should not happen in a "
                "background task context."
            )
        return docket

    async def elicit(
        self,
        message: str,
        response_type: type | None = None,
    ) -> Any:
        """Request user input, updating task status to input_required.

        This method implements the SEP-1686 ``input_required`` flow:

        1. Updates task status to ``input_required``
        2. Sends elicitation request with ``related-task`` metadata
        3. Waits for user response
        4. Updates task status back to ``working``
        5. Returns the parsed result

        Args:
            message: The message to display to the user
            response_type: The expected response type. Can be:

                - A dataclass or Pydantic model for structured input
                - A primitive type (str, int, bool, float) for simple input
                - None for freeform text input

        Returns:
            - ``AcceptedElicitation[T]`` if user accepted (data contains response)
            - ``DeclinedElicitation`` if user declined
            - ``CancelledElicitation`` if user cancelled

        Raises:
            RuntimeError: If session is no longer available
            McpError: If client doesn't support elicitation

        Example:
            .. code-block:: python

                @dataclass
                class UserInfo:
                    name: str
                    age: int

                @mcp.tool(task=True)
                async def get_info(task_ctx: TaskContext = CurrentTaskContext()):
                    result = await task_ctx.elicit(
                        message="Please provide your information",
                        response_type=UserInfo,
                    )
                    if result.action == "accept":
                        return f"{result.data.name} is {result.data.age} years old"
                    return "No info provided"
        """
        import anyio

        import mcp.shared.exceptions
        import mcp.shared.message
        import mcp.types
        from fastmcp.server.elicitation import (
            CancelledElicitation,
            DeclinedElicitation,
            handle_elicit_accept,
            parse_elicit_response_type,
        )
        from fastmcp.server.tasks.subscriptions import send_input_required_notification

        session = self._get_session()
        docket = self._get_docket()
        config = parse_elicit_response_type(response_type)

        try:
            # Update status to input_required
            await send_input_required_notification(
                session=session,
                task_id=self._task_id,
                session_id=self._session_id,
                docket=docket,
                status="input_required",
            )

            # Build the elicitation request with related-task metadata
            request = session._build_elicit_form_request(  # pyright: ignore[reportPrivateUsage]
                message=message,
                requestedSchema=config.schema,
                related_task_id=self._task_id,
            )

            # Send the request and wait for response
            response_stream, response_stream_reader = anyio.create_memory_object_stream[
                mcp.types.JSONRPCResponse | mcp.types.JSONRPCError
            ](1)
            request_id = request.id
            session._response_streams[request_id] = response_stream  # pyright: ignore[reportPrivateUsage]

            try:
                await session._write_stream.send(  # pyright: ignore[reportPrivateUsage]
                    mcp.shared.message.SessionMessage(
                        message=mcp.types.JSONRPCMessage(request)
                    )
                )

                response_or_error = await response_stream_reader.receive()

                if isinstance(response_or_error, mcp.types.JSONRPCError):
                    raise mcp.shared.exceptions.McpError(response_or_error.error)
                else:
                    result = mcp.types.ElicitResult.model_validate(
                        response_or_error.result
                    )
            finally:
                session._response_streams.pop(request_id, None)  # pyright: ignore[reportPrivateUsage]
                await response_stream.aclose()
                await response_stream_reader.aclose()

            # Parse and return result
            if result.action == "accept":
                return handle_elicit_accept(config, result.content)
            elif result.action == "decline":
                return DeclinedElicitation()
            elif result.action == "cancel":
                return CancelledElicitation()
            else:
                raise ValueError(f"Unexpected elicitation action: {result.action}")

        finally:
            # Always restore status to working
            await send_input_required_notification(
                session=session,
                task_id=self._task_id,
                session_id=self._session_id,
                docket=docket,
                status="working",
            )

    async def sample(
        self,
        messages: list[Any],
        *,
        max_tokens: int = 512,
        system_prompt: str | None = None,
        temperature: float | None = None,
        model_preferences: Any | None = None,
    ) -> Any:
        """Request model sampling, updating task status to input_required.

        This method implements the SEP-1686 ``input_required`` flow for sampling:

        1. Updates task status to ``input_required``
        2. Sends sampling request with ``related-task`` metadata
        3. Waits for LLM response
        4. Updates task status back to ``working``
        5. Returns the result

        Args:
            messages: The conversation messages for sampling
            max_tokens: Maximum tokens in the response (default: 512)
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            model_preferences: Optional model selection preferences

        Returns:
            CreateMessageResult from the client

        Raises:
            RuntimeError: If session is no longer available
            McpError: If client doesn't support sampling

        Example:
            .. code-block:: python

                @mcp.tool(task=True)
                async def summarize(
                    text: str,
                    task_ctx: TaskContext = CurrentTaskContext(),
                ) -> str:
                    result = await task_ctx.sample(
                        messages=[{"role": "user", "content": f"Summarize: {text}"}],
                        max_tokens=200,
                    )
                    return result.content.text
        """
        import anyio

        import mcp.shared.exceptions
        import mcp.shared.message
        import mcp.types
        from fastmcp.server.tasks.subscriptions import send_input_required_notification

        session = self._get_session()
        docket = self._get_docket()

        # Convert simple message dicts to SamplingMessage if needed
        sampling_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                from mcp.types import SamplingMessage, TextContent

                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, str):
                    content = TextContent(type="text", text=content)
                sampling_messages.append(SamplingMessage(role=role, content=content))
            else:
                sampling_messages.append(msg)

        try:
            # Update status to input_required
            await send_input_required_notification(
                session=session,
                task_id=self._task_id,
                session_id=self._session_id,
                docket=docket,
                status="input_required",
            )

            # Build the sampling request with related-task metadata
            request = session._build_create_message_request(  # pyright: ignore[reportPrivateUsage]
                messages=sampling_messages,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                temperature=temperature,
                model_preferences=model_preferences,
                related_task_id=self._task_id,
            )

            # Send the request and wait for response
            response_stream, response_stream_reader = anyio.create_memory_object_stream[
                mcp.types.JSONRPCResponse | mcp.types.JSONRPCError
            ](1)
            request_id = request.id
            session._response_streams[request_id] = response_stream  # pyright: ignore[reportPrivateUsage]

            try:
                await session._write_stream.send(  # pyright: ignore[reportPrivateUsage]
                    mcp.shared.message.SessionMessage(
                        message=mcp.types.JSONRPCMessage(request)
                    )
                )

                response_or_error = await response_stream_reader.receive()

                if isinstance(response_or_error, mcp.types.JSONRPCError):
                    raise mcp.shared.exceptions.McpError(response_or_error.error)
                else:
                    return mcp.types.CreateMessageResult.model_validate(
                        response_or_error.result
                    )
            finally:
                session._response_streams.pop(request_id, None)  # pyright: ignore[reportPrivateUsage]
                await response_stream.aclose()
                await response_stream_reader.aclose()

        finally:
            # Always restore status to working
            await send_input_required_notification(
                session=session,
                task_id=self._task_id,
                session_id=self._session_id,
                docket=docket,
                status="working",
            )


class _CurrentTaskContext(Dependency):  # type: ignore[misc]
    """Async context manager for TaskContext dependency."""

    async def __aenter__(self) -> TaskContext:
        task_info = get_task_context()
        if task_info is None:
            raise RuntimeError(
                "CurrentTaskContext() can only be used in background tasks. "
                "Add task=True to your component decorator, or use CurrentContext() "
                "for foreground operations."
            )
        return TaskContext(
            task_id=task_info.task_id,
            session_id=task_info.session_id,
        )

    async def __aexit__(self, *args: object) -> None:
        pass


def CurrentTaskContext() -> TaskContext:
    """Get the current TaskContext for background task operations.

    This dependency is ONLY available in background tasks (``task=True``).
    It provides access to elicitation and sampling with proper
    ``input_required`` status handling per SEP-1686.

    Unlike ``CurrentContext()``, which is NOT available in background tasks,
    ``CurrentTaskContext()`` IS available and provides a subset of Context
    functionality that works in the worker environment.

    Returns:
        A dependency that resolves to the active TaskContext

    Raises:
        RuntimeError: If not in a background task context (during resolution)

    Example:
        .. code-block:: python

            from fastmcp.dependencies import CurrentTaskContext, TaskContext

            @mcp.tool(task=True)
            async def my_task(task_ctx: TaskContext = CurrentTaskContext()) -> str:
                result = await task_ctx.elicit("Name?", response_type=str)
                if result.action == "accept":
                    return f"Hello, {result.data}!"
                return "No name"
    """
    require_docket("CurrentTaskContext()")
    return cast(TaskContext, _CurrentTaskContext())


# --- Progress dependency ---


@runtime_checkable
class ProgressLike(Protocol):
    """Protocol for progress tracking interface.

    Defines the common interface between InMemoryProgress (server context)
    and Docket's Progress (worker context).
    """

    @property
    def current(self) -> int | None:
        """Current progress value."""
        ...

    @property
    def total(self) -> int:
        """Total/target progress value."""
        ...

    @property
    def message(self) -> str | None:
        """Current progress message."""
        ...

    async def set_total(self, total: int) -> None:
        """Set the total/target value for progress tracking."""
        ...

    async def increment(self, amount: int = 1) -> None:
        """Atomically increment the current progress value."""
        ...

    async def set_message(self, message: str | None) -> None:
        """Update the progress status message."""
        ...


class InMemoryProgress:
    """In-memory progress tracker for immediate tool execution.

    Provides the same interface as Docket's Progress but stores state in memory
    instead of Redis. Useful for testing and immediate execution where
    progress doesn't need to be observable across processes.
    """

    def __init__(self) -> None:
        self._current: int | None = None
        self._total: int = 1
        self._message: str | None = None

    async def __aenter__(self) -> InMemoryProgress:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    @property
    def current(self) -> int | None:
        return self._current

    @property
    def total(self) -> int:
        return self._total

    @property
    def message(self) -> str | None:
        return self._message

    async def set_total(self, total: int) -> None:
        """Set the total/target value for progress tracking."""
        if total < 1:
            raise ValueError("Total must be at least 1")
        self._total = total

    async def increment(self, amount: int = 1) -> None:
        """Atomically increment the current progress value."""
        if amount < 1:
            raise ValueError("Amount must be at least 1")
        if self._current is None:
            self._current = amount
        else:
            self._current += amount

    async def set_message(self, message: str | None) -> None:
        """Update the progress status message."""
        self._message = message


class Progress(Dependency):  # type: ignore[misc]
    """FastMCP Progress dependency that works in both server and worker contexts.

    Handles three execution modes:
    - In Docket worker: Uses the execution's progress (observable via Redis)
    - In FastMCP server with Docket: Falls back to in-memory progress
    - In FastMCP server without Docket: Uses in-memory progress

    This allows tools to use Progress() regardless of whether they're called
    immediately or as background tasks, and regardless of whether pydocket
    is installed.
    """

    async def __aenter__(self) -> ProgressLike:
        # Check if we're in a FastMCP server context
        server_ref = _current_server.get()
        if server_ref is None or server_ref() is None:
            raise RuntimeError("Progress dependency requires a FastMCP server context.")

        # If pydocket is installed, try to use Docket's progress
        if is_docket_available():
            from docket.dependencies import Progress as DocketProgress

            # Try to get execution from Docket worker context
            try:
                docket_progress = DocketProgress()
                return await docket_progress.__aenter__()
            except LookupError:
                # Not in worker context - fall through to in-memory progress
                pass

        # Return in-memory progress for immediate execution
        # This is used when:
        # 1. pydocket is not installed
        # 2. Docket is not running (no task-enabled components)
        # 3. In server context (not worker context)
        return InMemoryProgress()

    async def __aexit__(self, *args: object) -> None:
        pass
