"""OpenAI-specific UI components and widgets."""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, cast, overload

from mcp.types import AnyFunction, ToolAnnotations

from fastmcp.tools.tool import FunctionTool
from fastmcp.ui.openai.metadata import (
    build_widget_resource_meta,
    build_widget_tool_meta,
    merge_resource_annotations,
    merge_tool_annotations,
)
from fastmcp.ui.openai.response import transform_widget_response

if TYPE_CHECKING:
    from fastmcp.server.server import FastMCP


class OpenAIUIManager:
    """Manager for OpenAI-specific UI components like widgets."""

    def __init__(self, fastmcp: FastMCP[Any]) -> None:
        self._fastmcp = fastmcp

    @overload
    def widget(
        self,
        name_or_fn: AnyFunction,
        *,
        identifier: str | None = None,
        template_uri: str,
        html: str,
        title: str | None = None,
        description: str | None = None,
        invoking: str | None = None,
        invoked: str | None = None,
        mime_type: str = "text/html+skybridge",
        widget_description: str | None = None,
        widget_prefers_border: bool = True,
        widget_csp_resources: Sequence[str] | None = None,
        widget_csp_connect: Sequence[str] | None = None,
        widget_accessible: bool = True,
        result_can_produce_widget: bool = True,
        tags: set[str] | None = None,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        resource_annotations: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        enabled: bool | None = None,
        exclude_args: list[str] | None = None,
    ) -> FunctionTool: ...

    @overload
    def widget(
        self,
        name_or_fn: str | None = None,
        *,
        identifier: str | None = None,
        template_uri: str,
        html: str,
        title: str | None = None,
        description: str | None = None,
        invoking: str | None = None,
        invoked: str | None = None,
        mime_type: str = "text/html+skybridge",
        widget_description: str | None = None,
        widget_prefers_border: bool = True,
        widget_csp_resources: Sequence[str] | None = None,
        widget_csp_connect: Sequence[str] | None = None,
        widget_accessible: bool = True,
        result_can_produce_widget: bool = True,
        tags: set[str] | None = None,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        resource_annotations: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        enabled: bool | None = None,
        exclude_args: list[str] | None = None,
    ) -> Callable[[AnyFunction], FunctionTool]: ...

    def widget(
        self,
        name_or_fn: str | AnyFunction | None = None,
        *,
        identifier: str | None = None,
        template_uri: str | None = None,
        html: str | None = None,
        title: str | None = None,
        description: str | None = None,
        invoking: str | None = None,
        invoked: str | None = None,
        mime_type: str = "text/html+skybridge",
        widget_description: str | None = None,
        widget_prefers_border: bool = True,
        widget_csp_resources: Sequence[str] | None = None,
        widget_csp_connect: Sequence[str] | None = None,
        widget_accessible: bool = True,
        result_can_produce_widget: bool = True,
        tags: set[str] | None = None,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        resource_annotations: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
        enabled: bool | None = None,
        exclude_args: list[str] | None = None,
    ) -> Callable[[AnyFunction], FunctionTool] | FunctionTool:
        """Register an OpenAI widget as a tool.

        OpenAI widgets are interactive UI components that display in ChatGPT.
        This decorator automatically:
        1. Registers widget HTML as an MCP resource
        2. Registers a tool with OpenAI metadata linking to the widget
        3. Auto-transforms function return values (str, dict, or tuple) to OpenAI format

        The widget function can return:
        - `str`: Narrative text shown in conversation (no structured data)
        - `dict`: Structured data passed to widget JavaScript (no narrative)
        - `tuple[str, dict]`: Both narrative text and structured data

        This decorator supports multiple calling patterns:
        - @server.ui.openai.widget(identifier=..., template_uri=..., html=...)
        - @server.ui.openai.widget("name", identifier=..., template_uri=..., html=...)

        Args:
            name_or_fn: Either a function (direct decoration) or string name
            identifier: Tool name (defaults to function name or name_or_fn if str)
            template_uri: Widget template URI (e.g. "ui://widget/pizza-map.html")
            html: Widget HTML content (must include div and script tags)
            title: Widget display title (defaults to identifier)
            description: Tool description (defaults to function docstring)
            invoking: Status message while tool executes (e.g. "Hand-tossing a map")
            invoked: Status message after tool completes (e.g. "Served a fresh map")
            mime_type: MIME type for widget HTML (default: "text/html+skybridge")
            widget_description: Description of widget UI (defaults to "{title} widget UI.")
            widget_prefers_border: Whether widget prefers a border (default: True)
            widget_csp_resources: CSP resource_domains (default: ["https://persistent.oaistatic.com"])
            widget_csp_connect: CSP connect_domains (default: [])
            widget_accessible: Whether widget is accessible (default: True)
            result_can_produce_widget: Whether result can produce widget (default: True)
            tags: Tags for categorizing the widget
            annotations: Tool annotations (merged with widget defaults)
            resource_annotations: Resource annotations for HTML resource
            meta: Additional tool metadata (merged with widget metadata)
            enabled: Whether widget is enabled (default: True)
            exclude_args: Arguments to exclude from tool schema

        Returns:
            Decorated function registered as a widget tool

        Examples:
            Register a widget with data only:
            ```python
            @app.ui.openai.widget(
                identifier="pizza-map",
                template_uri="ui://widget/pizza-map.html",
                html='<div id="root"></div><script src="..."></script>',
                invoking="Hand-tossing a map",
                invoked="Served a fresh map"
            )
            def show_pizza_map(topping: str) -> dict:
                \"\"\"Show a pizza map for the given topping.\"\"\"
                return {"topping": topping}  # Auto-transformed!
            ```

            Register a widget with both text and data:
            ```python
            @app.ui.openai.widget(
                identifier="weather",
                template_uri="ui://widget/weather.html",
                html='<div id="weather"></div>...'
            )
            def show_weather(city: str) -> tuple[str, dict]:
                return (f"Showing weather for {city}", {"city": city, "temp": 72})
            ```

            Register a widget with text only:
            ```python
            @app.ui.openai.widget(
                identifier="status",
                template_uri="ui://widget/status.html",
                html='<div id="status"></div>...'
            )
            def show_status() -> str:
                return "Status widget displayed"
            ```
        """
        # Validate required parameters
        if template_uri is None:
            raise TypeError("widget() missing required keyword argument: 'template_uri'")
        if html is None:
            raise TypeError("widget() missing required keyword argument: 'html'")

        if isinstance(annotations, dict):
            annotations = ToolAnnotations(**annotations)

        if isinstance(name_or_fn, classmethod):
            raise ValueError(
                inspect.cleandoc(
                    """
                    To decorate a classmethod, first define the method and then call
                    widget() directly on the method instead of using it as a
                    decorator. See https://gofastmcp.com/patterns/decorating-methods
                    for examples and more information.
                    """
                )
            )

        # Determine the widget identifier and function based on calling pattern
        if inspect.isroutine(name_or_fn):
            # Case 1: @widget(template_uri=..., html=...) - function passed directly
            fn = name_or_fn
            widget_identifier = identifier or fn.__name__

            # Register immediately and return
            return self._register_widget(
                fn=fn,
                identifier=widget_identifier,
                template_uri=template_uri,
                html=html,
                title=title,
                description=description,
                invoking=invoking,
                invoked=invoked,
                mime_type=mime_type,
                widget_description=widget_description,
                widget_prefers_border=widget_prefers_border,
                widget_csp_resources=widget_csp_resources,
                widget_csp_connect=widget_csp_connect,
                widget_accessible=widget_accessible,
                result_can_produce_widget=result_can_produce_widget,
                tags=tags,
                annotations=cast(ToolAnnotations | None, annotations),
                resource_annotations=resource_annotations,
                meta=meta,
                enabled=enabled,
                exclude_args=exclude_args,
            )

        elif isinstance(name_or_fn, str):
            # Case 2: @widget("custom_name", template_uri=..., html=...)
            if identifier is not None:
                raise TypeError(
                    "Cannot specify both a name as first argument and as keyword argument. "
                    f"Use either @widget('{name_or_fn}', ...) or @widget(identifier='{identifier}', ...), not both."
                )
            widget_identifier = name_or_fn
        elif name_or_fn is None:
            # Case 3: @widget(identifier="name", template_uri=..., html=...)
            widget_identifier = identifier
        else:
            raise TypeError(
                f"First argument to @widget must be a function, string, or None, got {type(name_or_fn)}"
            )

        # Return decorator that will be applied to the function
        def decorator(fn: AnyFunction) -> FunctionTool:
            actual_identifier = widget_identifier or fn.__name__
            return self._register_widget(
                fn=fn,
                identifier=actual_identifier,
                template_uri=template_uri,
                html=html,
                title=title,
                description=description,
                invoking=invoking,
                invoked=invoked,
                mime_type=mime_type,
                widget_description=widget_description,
                widget_prefers_border=widget_prefers_border,
                widget_csp_resources=widget_csp_resources,
                widget_csp_connect=widget_csp_connect,
                widget_accessible=widget_accessible,
                result_can_produce_widget=result_can_produce_widget,
                tags=tags,
                annotations=cast(ToolAnnotations | None, annotations),
                resource_annotations=resource_annotations,
                meta=meta,
                enabled=enabled,
                exclude_args=exclude_args,
            )

        return decorator

    def _register_widget(
        self,
        *,
        fn: AnyFunction,
        identifier: str,
        template_uri: str,
        html: str,
        title: str | None,
        description: str | None,
        invoking: str | None,
        invoked: str | None,
        mime_type: str,
        widget_description: str | None,
        widget_prefers_border: bool,
        widget_csp_resources: Sequence[str] | None,
        widget_csp_connect: Sequence[str] | None,
        widget_accessible: bool,
        result_can_produce_widget: bool,
        tags: set[str] | None,
        annotations: ToolAnnotations | None,
        resource_annotations: dict[str, Any] | None,
        meta: dict[str, Any] | None,
        enabled: bool | None,
        exclude_args: list[str] | None,
    ) -> FunctionTool:
        """Internal method to register a widget.

        This orchestrates:
        1. Registering the widget HTML as a resource
        2. Wrapping the function to auto-transform return values
        3. Registering the wrapped function as a tool with OpenAI metadata
        """
        # Use title or default to identifier
        widget_title = title or identifier

        # Step 1: Register widget HTML as a resource
        self._register_widget_resource(
            template_uri=template_uri,
            html=html,
            title=widget_title,
            mime_type=mime_type,
            widget_description=widget_description,
            widget_prefers_border=widget_prefers_border,
            widget_csp_resources=widget_csp_resources,
            widget_csp_connect=widget_csp_connect,
            resource_annotations=resource_annotations,
        )

        # Step 2: Wrap function to auto-transform return values
        wrapped_fn = self._wrap_widget_function(fn)

        # Step 3: Build OpenAI widget metadata for the tool
        widget_meta = build_widget_tool_meta(
            template_uri=template_uri,
            html=html,
            title=widget_title,
            invoking=invoking,
            invoked=invoked,
            mime_type=mime_type,
            widget_description=widget_description,
            widget_prefers_border=widget_prefers_border,
            widget_csp_resources=widget_csp_resources,
            widget_csp_connect=widget_csp_connect,
            widget_accessible=widget_accessible,
            result_can_produce_widget=result_can_produce_widget,
            additional_meta=meta,
        )

        # Merge tool annotations with widget defaults
        merged_annotations = merge_tool_annotations(
            annotations.model_dump() if annotations else None
        )

        # Step 4: Register as a tool with widget metadata
        from fastmcp.tools.tool import Tool

        tool = Tool.from_function(
            wrapped_fn,
            name=identifier,
            title=title,
            description=description,
            tags=tags,
            annotations=ToolAnnotations(**merged_annotations),
            exclude_args=exclude_args,
            meta=widget_meta,
            serializer=self._fastmcp._tool_serializer,
            enabled=enabled,
        )
        self._fastmcp.add_tool(tool)
        return tool

    def _register_widget_resource(
        self,
        *,
        template_uri: str,
        html: str,
        title: str,
        mime_type: str,
        widget_description: str | None,
        widget_prefers_border: bool,
        widget_csp_resources: Sequence[str] | None,
        widget_csp_connect: Sequence[str] | None,
        resource_annotations: dict[str, Any] | None,
    ) -> None:
        """Register widget HTML as an MCP resource."""
        # Build resource metadata
        resource_meta = build_widget_resource_meta(
            title=title,
            widget_description=widget_description,
            widget_prefers_border=widget_prefers_border,
            widget_csp_resources=widget_csp_resources,
            widget_csp_connect=widget_csp_connect,
        )

        # Merge resource annotations
        merged_resource_annotations = merge_resource_annotations(resource_annotations)

        # Register the resource using FastMCP's resource decorator
        @self._fastmcp.resource(
            uri=template_uri,
            name=title,
            description=f"{title} widget markup",
            mime_type=mime_type,
            annotations=merged_resource_annotations,
            meta=resource_meta,
        )
        def widget_html_resource() -> str:
            return html

    def _wrap_widget_function(self, fn: AnyFunction) -> AnyFunction:
        """Wrap a widget function to auto-transform return values.

        The wrapper intercepts the function's return value and transforms it
        to the OpenAI format: {"content": [...], "structuredContent": {...}}

        Supports sync and async functions.
        """
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
                result = await fn(*args, **kwargs)
                return transform_widget_response(result)

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
                result = fn(*args, **kwargs)
                return transform_widget_response(result)

            return sync_wrapper
