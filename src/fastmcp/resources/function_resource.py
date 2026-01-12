"""Standalone @resource decorator for FastMCP."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeAlias, runtime_checkable

from mcp.types import Annotations, Icon

import fastmcp
from fastmcp.decorators import resolve_task_config
from fastmcp.server.tasks.config import TaskConfig

if TYPE_CHECKING:
    from fastmcp.resources.resource import Resource
    from fastmcp.resources.template import ResourceTemplate

AnyFunction: TypeAlias = Callable[..., Any]


@runtime_checkable
class DecoratedResource(Protocol):
    """Protocol for functions decorated with @resource."""

    __fastmcp__: ResourceMeta

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, kw_only=True)
class ResourceMeta:
    """Metadata attached to functions by the @resource decorator."""

    type: Literal["resource"] = field(default="resource", init=False)
    uri: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    icons: list[Icon] | None = None
    tags: set[str] | None = None
    mime_type: str | None = None
    annotations: Annotations | None = None
    meta: dict[str, Any] | None = None
    task: bool | TaskConfig | None = None


def resource(
    uri: str,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    icons: list[Icon] | None = None,
    mime_type: str | None = None,
    tags: set[str] | None = None,
    annotations: Annotations | dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
) -> Callable[[AnyFunction], Resource | ResourceTemplate | AnyFunction]:
    """Standalone decorator to mark a function as an MCP resource.

    Returns the original function with metadata attached. Register with a server
    using mcp.add_resource().
    """
    if isinstance(annotations, dict):
        annotations = Annotations(**annotations)

    if inspect.isroutine(uri):
        raise TypeError(
            "The @resource decorator requires a URI. "
            "Use @resource('uri') instead of @resource"
        )

    def create_resource(fn: AnyFunction) -> Resource | ResourceTemplate:
        from fastmcp.resources.resource import Resource as ResourceClass
        from fastmcp.resources.template import ResourceTemplate
        from fastmcp.server.dependencies import without_injected_parameters

        resolved = resolve_task_config(task)
        has_uri_params = "{" in uri and "}" in uri
        wrapper_fn = without_injected_parameters(fn)
        has_func_params = bool(inspect.signature(wrapper_fn).parameters)

        if has_uri_params or has_func_params:
            return ResourceTemplate.from_function(
                fn=fn,
                uri_template=uri,
                name=name,
                title=title,
                description=description,
                icons=icons,
                mime_type=mime_type,
                tags=tags,
                annotations=annotations,
                meta=meta,
                task=resolved,
            )
        else:
            return ResourceClass.from_function(
                fn=fn,
                uri=uri,
                name=name,
                title=title,
                description=description,
                icons=icons,
                mime_type=mime_type,
                tags=tags,
                annotations=annotations,
                meta=meta,
                task=resolved,
            )

    def attach_metadata(fn: AnyFunction) -> AnyFunction:
        metadata = ResourceMeta(
            uri=uri,
            name=name,
            title=title,
            description=description,
            icons=icons,
            tags=tags,
            mime_type=mime_type,
            annotations=annotations,
            meta=meta,
            task=task,
        )
        target = fn.__func__ if hasattr(fn, "__func__") else fn
        target.__fastmcp__ = metadata  # type: ignore[attr-defined]
        return fn

    def decorator(fn: AnyFunction) -> Resource | ResourceTemplate | AnyFunction:
        if fastmcp.settings.decorator_mode == "object":
            return create_resource(fn)
        return attach_metadata(fn)

    return decorator
