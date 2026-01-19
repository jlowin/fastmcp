"""Resource decorator for LocalProvider."""

import inspect
from collections.abc import Callable
from typing import Any

import mcp.types
from mcp.types import Annotations, AnyFunction

import fastmcp
from fastmcp.resources.function_resource import resource as standalone_resource
from fastmcp.resources.resource import Resource
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.providers.local_provider.local_provider import LocalProvider
from fastmcp.server.tasks.config import TaskConfig
from fastmcp.tools.tool import AuthCheckCallable


def resource(
    self: LocalProvider,
    uri: str,
    *,
    name: str | None = None,
    version: str | int | None = None,
    title: str | None = None,
    description: str | None = None,
    icons: list[mcp.types.Icon] | None = None,
    mime_type: str | None = None,
    tags: set[str] | None = None,
    enabled: bool = True,
    annotations: Annotations | dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    task: bool | TaskConfig | None = None,
    auth: AuthCheckCallable | list[AuthCheckCallable] | None = None,
) -> Callable[[AnyFunction], Resource | ResourceTemplate | AnyFunction]:
    """Decorator to register a function as a resource.

    If the URI contains parameters (e.g. "resource://{param}") or the function
    has parameters, it will be registered as a template resource.

    Args:
        uri: URI for the resource (e.g. "resource://my-resource" or "resource://{param}")
        name: Optional name for the resource
        title: Optional title for the resource
        description: Optional description of the resource
        icons: Optional icons for the resource
        mime_type: Optional MIME type for the resource
        tags: Optional set of tags for categorizing the resource
        enabled: Whether the resource is enabled (default True). If False, adds to blocklist.
        annotations: Optional annotations about the resource's behavior
        meta: Optional meta information about the resource
        task: Optional task configuration for background execution
        auth: Optional authorization checks for the resource

    Returns:
        A decorator function.

    Example:
        ```python
        provider = LocalProvider()

        @provider.resource("data://config")
        def get_config() -> str:
            return '{"setting": "value"}'

        @provider.resource("data://{city}/weather")
        def get_weather(city: str) -> str:
            return f"Weather for {city}"
        ```
    """
    if isinstance(annotations, dict):
        annotations = Annotations(**annotations)

    if inspect.isroutine(uri):
        raise TypeError(
            "The @resource decorator was used incorrectly. "
            "It requires a URI as the first argument. "
            "Use @resource('uri') instead of @resource"
        )

    resolved_task: bool | TaskConfig = task if task is not None else False

    def decorator(fn: AnyFunction) -> Resource | ResourceTemplate | AnyFunction:
        # Check for unbound method
        try:
            params = list(inspect.signature(fn).parameters.keys())
        except (ValueError, TypeError):
            params = []
        if params and params[0] in ("self", "cls"):
            fn_name = getattr(fn, "__name__", "function")
            raise TypeError(
                f"The function '{fn_name}' has '{params[0]}' as its first parameter. "
                f"Use the standalone @resource decorator and register the bound method:\n\n"
                f"    from fastmcp.resources import resource\n\n"
                f"    class MyClass:\n"
                f"        @resource('{uri}')\n"
                f"        def {fn_name}(...):\n"
                f"            ...\n\n"
                f"    obj = MyClass()\n"
                f"    mcp.add_resource(obj.{fn_name})\n\n"
                f"See https://gofastmcp.com/servers/resources#using-with-methods"
            )

        if fastmcp.settings.decorator_mode == "object":
            create_resource = standalone_resource(
                uri,
                name=name,
                version=version,
                title=title,
                description=description,
                icons=icons,
                mime_type=mime_type,
                tags=tags,
                annotations=annotations,
                meta=meta,
                task=resolved_task,
                auth=auth,
            )
            obj = create_resource(fn)
            # In legacy mode, standalone_resource always returns a component
            assert isinstance(obj, (Resource, ResourceTemplate))
            if isinstance(obj, ResourceTemplate):
                self.add_template(obj)
                if not enabled:
                    self.disable(keys={obj.key})
            else:
                self.add_resource(obj)
                if not enabled:
                    self.disable(keys={obj.key})
            return obj
        else:
            from fastmcp.resources.function_resource import ResourceMeta

            metadata = ResourceMeta(
                uri=uri,
                name=name,
                version=version,
                title=title,
                description=description,
                icons=icons,
                tags=tags,
                mime_type=mime_type,
                annotations=annotations,
                meta=meta,
                task=task,
                auth=auth,
                enabled=enabled,
            )
            target = fn.__func__ if hasattr(fn, "__func__") else fn
            target.__fastmcp__ = metadata  # type: ignore[attr-defined]
            self.add_resource(fn)
            return fn

    return decorator
