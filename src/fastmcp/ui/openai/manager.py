"""OpenAI-specific UI components and widgets."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any, cast, overload

from mcp.types import AnyFunction, ToolAnnotations

from fastmcp.tools.tool import FunctionTool, Tool
from fastmcp.utilities.types import NotSet, NotSetT

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
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        output_schema: dict[str, Any] | None | NotSetT = NotSet,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        exclude_args: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> FunctionTool: ...

    @overload
    def widget(
        self,
        name_or_fn: str | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        output_schema: dict[str, Any] | None | NotSetT = NotSet,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        exclude_args: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], FunctionTool]: ...

    def widget(
        self,
        name_or_fn: str | AnyFunction | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        output_schema: dict[str, Any] | None | NotSetT = NotSet,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        exclude_args: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], FunctionTool] | FunctionTool:
        """Decorator to register an OpenAI widget as a tool.

        OpenAI widgets are tools that can be called by OpenAI's assistants and displayed
        in custom UIs. This decorator works identically to @server.tool but provides
        semantic clarity for UI-focused functionality.

        This decorator supports multiple calling patterns:
        - @server.ui.openai.widget (without parentheses)
        - @server.ui.openai.widget() (with empty parentheses)
        - @server.ui.openai.widget("custom_name") (with name as first argument)
        - @server.ui.openai.widget(name="custom_name") (with name as keyword argument)

        Args:
            name_or_fn: Either a function (when used as decorator), a string name, or None
            name: Optional name for the widget (keyword-only, alternative to name_or_fn)
            title: Optional title for the widget
            description: Optional description of what the widget does
            tags: Optional set of tags for categorizing the widget
            output_schema: Optional JSON schema for the widget's output
            annotations: Optional annotations about the widget's behavior
            exclude_args: Optional list of argument names to exclude from the schema
            meta: Optional meta information about the widget
            enabled: Optional boolean to enable or disable the widget

        Examples:
            Register an OpenAI widget:
            ```python
            @app.ui.openai.widget
            def my_widget(x: int) -> str:
                return str(x)

            @app.ui.openai.widget("custom_name")
            def another_widget(data: str) -> dict:
                return {"result": data}

            @app.ui.openai.widget(name="weather_display")
            def show_weather(city: str) -> str:
                return f"Weather for {city}"
            ```
        """
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

        # Determine the actual name and function based on the calling pattern
        if inspect.isroutine(name_or_fn):
            # Case 1: @widget (without parens) - function passed directly
            # Case 2: direct call like widget(fn, name="something")
            fn = name_or_fn
            widget_name = name  # Use keyword name if provided, otherwise None

            # Register the widget as a tool immediately and return the tool object
            tool = Tool.from_function(
                fn,
                name=widget_name,
                title=title,
                description=description,
                tags=tags,
                output_schema=output_schema,
                annotations=cast(ToolAnnotations | None, annotations),
                exclude_args=exclude_args,
                meta=meta,
                serializer=self._fastmcp._tool_serializer,
                enabled=enabled,
            )
            self._fastmcp.add_tool(tool)
            return tool

        elif isinstance(name_or_fn, str):
            # Case 3: @widget("custom_name") - name passed as first argument
            if name is not None:
                raise TypeError(
                    "Cannot specify both a name as first argument and as keyword argument. "
                    f"Use either @widget('{name_or_fn}') or @widget(name='{name}'), not both."
                )
            widget_name = name_or_fn
        elif name_or_fn is None:
            # Case 4: @widget or @widget(name="something") - use keyword name
            widget_name = name
        else:
            raise TypeError(
                f"First argument to @widget must be a function, string, or None, got {type(name_or_fn)}"
            )

        # Return partial for cases where we need to wait for the function
        return partial(
            self.widget,
            name=widget_name,
            title=title,
            description=description,
            tags=tags,
            output_schema=output_schema,
            annotations=annotations,
            exclude_args=exclude_args,
            meta=meta,
            enabled=enabled,
        )
