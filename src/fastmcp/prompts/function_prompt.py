"""Standalone @prompt decorator for FastMCP."""

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

from mcp.types import Icon

import fastmcp
from fastmcp.decorators import resolve_task_config
from fastmcp.server.tasks.config import TaskConfig

if TYPE_CHECKING:
    from fastmcp.prompts.prompt import FunctionPrompt as FunctionPromptType

AnyFunction: TypeAlias = Callable[..., Any]


@runtime_checkable
class DecoratedPrompt(Protocol):
    """Protocol for functions decorated with @prompt."""

    __fastmcp__: PromptMeta

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, kw_only=True)
class PromptMeta:
    """Metadata attached to functions by the @prompt decorator."""

    type: Literal["prompt"] = field(default="prompt", init=False)
    name: str | None = None
    title: str | None = None
    description: str | None = None
    icons: list[Icon] | None = None
    tags: set[str] | None = None
    meta: dict[str, Any] | None = None
    task: bool | TaskConfig | None = None


@overload
def prompt(fn: AnyFunction) -> FunctionPromptType | AnyFunction: ...
@overload
def prompt(
    name_or_fn: str,
    *,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    tags: set[str] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
) -> Callable[[AnyFunction], FunctionPromptType | AnyFunction]: ...
@overload
def prompt(
    name_or_fn: None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    tags: set[str] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
) -> Callable[[AnyFunction], FunctionPromptType | AnyFunction]: ...


def prompt(
    name_or_fn: str | AnyFunction | None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    tags: set[str] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
) -> (
    Callable[[AnyFunction], FunctionPromptType | AnyFunction]
    | FunctionPromptType
    | AnyFunction
):
    """Standalone decorator to mark a function as an MCP prompt.

    Returns the original function with metadata attached. Register with a server
    using mcp.add_prompt().
    """
    if isinstance(name_or_fn, classmethod):
        raise TypeError(
            "To decorate a classmethod, use @classmethod above @prompt. "
            "See https://gofastmcp.com/patterns/decorating-methods"
        )

    def create_prompt(fn: AnyFunction, prompt_name: str | None) -> FunctionPromptType:
        from fastmcp.prompts.prompt import Prompt

        return Prompt.from_function(
            fn=fn,
            name=prompt_name,
            title=title,
            description=description,
            icons=icons,
            tags=tags,
            meta=meta,
            task=resolve_task_config(task),
        )

    def attach_metadata(fn: AnyFunction, prompt_name: str | None) -> AnyFunction:
        metadata = PromptMeta(
            name=prompt_name,
            title=title,
            description=description,
            icons=icons,
            tags=tags,
            meta=meta,
            task=task,
        )
        target = fn.__func__ if hasattr(fn, "__func__") else fn
        target.__fastmcp__ = metadata  # type: ignore[attr-defined]
        return fn

    def decorator(
        fn: AnyFunction, prompt_name: str | None
    ) -> FunctionPromptType | AnyFunction:
        if fastmcp.settings.decorator_mode == "object":
            return create_prompt(fn, prompt_name)
        return attach_metadata(fn, prompt_name)

    if inspect.isroutine(name_or_fn):
        return decorator(name_or_fn, name)
    elif isinstance(name_or_fn, str):
        if name is not None:
            raise TypeError("Cannot specify name both as first argument and keyword")
        prompt_name = name_or_fn
    elif name_or_fn is None:
        prompt_name = name
    else:
        raise TypeError(f"Invalid first argument: {type(name_or_fn)}")

    def wrapper(fn: AnyFunction) -> FunctionPromptType | AnyFunction:
        return decorator(fn, prompt_name)

    return wrapper
