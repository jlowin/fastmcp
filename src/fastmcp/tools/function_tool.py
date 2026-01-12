"""Standalone @tool decorator for FastMCP."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypeAlias,
    overload,
    runtime_checkable,
)

from mcp.types import Icon, ToolAnnotations

import fastmcp
from fastmcp.decorators import resolve_task_config
from fastmcp.server.tasks.config import TaskConfig
from fastmcp.utilities.types import NotSet, NotSetT

if TYPE_CHECKING:
    from fastmcp.tools.tool import FunctionTool as FunctionToolType

AnyFunction: TypeAlias = Callable[..., Any]


@runtime_checkable
class DecoratedTool(Protocol):
    """Protocol for functions decorated with @tool."""

    __fastmcp__: ToolMeta

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, kw_only=True)
class ToolMeta:
    """Metadata attached to functions by the @tool decorator."""

    type: Literal["tool"] = field(default="tool", init=False)
    name: str | None = None
    title: str | None = None
    description: str | None = None
    icons: list[Icon] | None = None
    tags: set[str] | None = None
    output_schema: dict[str, Any] | NotSetT | None = NotSet
    annotations: ToolAnnotations | None = None
    meta: dict[str, Any] | None = None
    task: bool | TaskConfig | None = None
    exclude_args: list[str] | None = None
    serializer: Any | None = None


@overload
def tool(fn: AnyFunction) -> FunctionToolType | AnyFunction: ...
@overload
def tool(
    name_or_fn: str,
    *,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    tags: set[str] | None = None,
    output_schema: dict[str, Any] | NotSetT | None = NotSet,
    annotations: ToolAnnotations | dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
    exclude_args: list[str] | None = None,
    serializer: Any | None = None,
) -> Callable[[AnyFunction], FunctionToolType | AnyFunction]: ...
@overload
def tool(
    name_or_fn: None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    tags: set[str] | None = None,
    output_schema: dict[str, Any] | NotSetT | None = NotSet,
    annotations: ToolAnnotations | dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
    exclude_args: list[str] | None = None,
    serializer: Any | None = None,
) -> Callable[[AnyFunction], FunctionToolType | AnyFunction]: ...


def tool(
    name_or_fn: str | AnyFunction | None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    tags: set[str] | None = None,
    output_schema: dict[str, Any] | NotSetT | None = NotSet,
    annotations: ToolAnnotations | dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
    exclude_args: list[str] | None = None,
    serializer: Any | None = None,
) -> (
    Callable[[AnyFunction], FunctionToolType | AnyFunction]
    | FunctionToolType
    | AnyFunction
):
    """Standalone decorator to mark a function as an MCP tool.

    Returns the original function with metadata attached. Register with a server
    using mcp.add_tool().
    """
    if isinstance(annotations, dict):
        annotations = ToolAnnotations(**annotations)

    if isinstance(name_or_fn, classmethod):
        raise TypeError(
            "To decorate a classmethod, use @classmethod above @tool. "
            "See https://gofastmcp.com/patterns/decorating-methods"
        )

    def create_tool(fn: AnyFunction, tool_name: str | None) -> FunctionToolType:
        from fastmcp.tools.tool import Tool

        return Tool.from_function(
            fn,
            name=tool_name,
            title=title,
            description=description,
            icons=icons,
            tags=tags,
            output_schema=output_schema,
            annotations=annotations,
            meta=meta,
            task=resolve_task_config(task),
            exclude_args=exclude_args,
            serializer=serializer,
        )

    def attach_metadata(fn: AnyFunction, tool_name: str | None) -> AnyFunction:
        metadata = ToolMeta(
            name=tool_name,
            title=title,
            description=description,
            icons=icons,
            tags=tags,
            output_schema=output_schema,
            annotations=annotations,
            meta=meta,
            task=task,
            exclude_args=exclude_args,
            serializer=serializer,
        )
        target = fn.__func__ if hasattr(fn, "__func__") else fn
        target.__fastmcp__ = metadata  # type: ignore[attr-defined]
        return fn

    def decorator(
        fn: AnyFunction, tool_name: str | None
    ) -> FunctionToolType | AnyFunction:
        if fastmcp.settings.decorator_mode == "object":
            return create_tool(fn, tool_name)
        return attach_metadata(fn, tool_name)

    if inspect.isroutine(name_or_fn):
        return decorator(name_or_fn, name)
    elif isinstance(name_or_fn, str):
        if name is not None:
            raise TypeError("Cannot specify name both as first argument and keyword")
        tool_name = name_or_fn
    elif name_or_fn is None:
        tool_name = name
    else:
        raise TypeError(f"Invalid first argument: {type(name_or_fn)}")

    def wrapper(fn: AnyFunction) -> FunctionToolType | AnyFunction:
        return decorator(fn, tool_name)

    return wrapper
