"""JMESPath filtering decorator for MCP tools.

Adds a `jmespath` parameter to tools that allows filtering/transforming results
before returning them, reducing response size for large datasets.

Requires the `jmespath` package: `pip install fastmcp[jmespath]`

Example:
    from fastmcp import FastMCP
    from fastmcp.contrib.jmespath_tools import filterable

    mcp = FastMCP("My Server")

    @mcp.tool
    @filterable
    async def get_logs(limit: int = 100):
        logs = await fetch_logs(limit)
        return {"success": True, "data": {"logs": logs}, "error": None}

    # Client can now filter results:
    # get_logs(limit=100, jmespath="data.logs[?level == 'ERROR'].message")
"""

import inspect
from functools import wraps
from typing import Annotated, Any

from pydantic import Field
from typing_extensions import TypedDict


def _get_jmespath():
    """Lazy import of jmespath with helpful error message."""
    try:
        import jmespath

        return jmespath
    except ImportError as e:
        raise ImportError(
            "jmespath package is required for @filterable decorator. "
            "Install it with: pip install fastmcp[jmespath]"
        ) from e


class ToolResult(TypedDict):
    """Standard result wrapper for filterable tools.

    Using a consistent wrapper allows jmespath filtering to work
    without breaking schema validation - the filter transforms
    the `data` field while keeping the wrapper structure intact.

    Attributes:
        success: Whether the tool call succeeded.
        data: The actual content - original or filtered by jmespath.
        error: Error message if success is False, None otherwise.
    """

    success: bool
    data: Any
    error: str | None


# Type alias for the jmespath parameter with description
JmespathParam = Annotated[
    str | None,
    Field(
        default=None,
        description="JMESPath expression to filter/project the result. "
        "Examples: 'data.items[*].name' (extract values), "
        "'data.items[?status == `active`]' (filter items), "
        "'{count: length(data.items), names: data.items[*].name}' (project fields)",
    ),
]


def filterable(fn):
    """Decorator that adds jmespath filtering to a tool.

    The decorated tool should return a dict with at least a `data` field
    containing the content to filter. The standard pattern is to return
    a ToolResult dict with {success, data, error}.

    The jmespath filter applies to the entire result dict, so use
    expressions like `data.items[*].name` to access nested data.

    Usage:
        @mcp.tool
        @filterable
        async def get_items(limit: int = 10) -> ToolResult:
            items = await fetch_items(limit)
            return {"success": True, "data": {"items": items}, "error": None}

        # Without filter - returns full result
        await get_items(limit=100)
        # Returns: {"success": true, "data": {"items": [...]}, "error": null}

        # With filter - returns transformed data
        await get_items(limit=100, jmespath="data.items[*].name")
        # Returns: {"success": true, "data": ["name1", "name2", ...], "error": null}

    Args:
        fn: The tool function to wrap.

    Returns:
        Wrapped function with jmespath parameter added.
    """
    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapper(
            *args, jmespath: str | None = None, **kwargs
        ) -> ToolResult:
            result = await fn(*args, **kwargs)
            return _apply_filter(result, jmespath)

        wrapper = async_wrapper
    else:

        @wraps(fn)
        def sync_wrapper(*args, jmespath: str | None = None, **kwargs) -> ToolResult:
            result = fn(*args, **kwargs)
            return _apply_filter(result, jmespath)

        wrapper = sync_wrapper

    # Update signature to include jmespath parameter
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    params.append(
        inspect.Parameter(
            "jmespath",
            inspect.Parameter.KEYWORD_ONLY,
            default=None,
            annotation=JmespathParam,
        )
    )
    wrapper.__signature__ = sig.replace(parameters=params)

    # Update annotations with jmespath param and ToolResult return type
    wrapper.__annotations__ = {
        **{k: v for k, v in fn.__annotations__.items() if k != "return"},
        "jmespath": JmespathParam,
        "return": ToolResult,
    }

    return wrapper


def _apply_filter(result: dict, jmespath_expr: str | None) -> ToolResult:
    """Apply jmespath filter to result if provided.

    Args:
        result: The tool result dict.
        jmespath_expr: JMESPath expression to apply, or None.

    Returns:
        ToolResult with filtered data if expression provided,
        or original result if no expression or if result indicates failure.
    """
    if not jmespath_expr:
        return result

    # Don't filter failed results
    if not result.get("success", True):
        return result

    jmespath_lib = _get_jmespath()

    try:
        filtered = jmespath_lib.search(jmespath_expr, result)
        return {"success": True, "data": filtered, "error": None}
    except jmespath_lib.exceptions.JMESPathError as e:
        return {"success": False, "data": None, "error": f"JMESPath error: {e}"}
