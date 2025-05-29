from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Annotated, Any

from jsonschema import ValidationError, validate
from mcp.types import EmbeddedResource, ImageContent, TextContent

from fastmcp.contrib.tool_transformer.models import (
    PostToolCallHookProtocol,
    PreToolCallHookProtocol,
    ToolOverride,
    ToolParameterTypes,
)
from fastmcp.exceptions import ToolError
from fastmcp.server.server import FastMCP
from fastmcp.tools.tool import Tool as FastMCPTool
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


def _extract_hook_args(
    extra_parameters: list[ToolParameterTypes],
    tool_call_kwargs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Extracts the hook arguments from the tool call kwargs.
    """
    hook_args: dict[str, Any] = {}
    tool_call_args: dict[str, Any] = deepcopy(tool_call_kwargs)

    extra_parameters_by_name = {
        extra_parameter.name: extra_parameter for extra_parameter in extra_parameters
    }

    for tool_arg_name in tool_call_kwargs:
        if tool_arg_name in extra_parameters_by_name:
            hook_args[tool_arg_name] = tool_call_args.pop(tool_arg_name)

    return hook_args, tool_call_args


def _apply_hook_parameters(
    schema: dict[str, Any],
    hook_parameters: list[ToolParameterTypes],
) -> dict[str, Any]:
    """Applies extra parameters for hooks to the tool parameters schema."""
    transformed_schema = deepcopy(schema)

    for hook_parameter in hook_parameters:
        transformed_schema = hook_parameter.add_into_schema(transformed_schema)

    return transformed_schema


def _apply_parameter_overrides(
    schema: dict[str, Any],
    overrides: list[ToolParameterTypes],
) -> dict[str, Any]:
    """
    Applies parameter overrides to a schema.
    """
    transformed_schema = deepcopy(schema)

    for override in overrides:
        transformed_schema = override.merge_into_schema(transformed_schema)

    return transformed_schema


def _create_transformed_function(
    original_tool_run_method: Callable[
        ..., Awaitable[list[TextContent | ImageContent | EmbeddedResource]]
    ],
    fn_transformed_parameters_schema: dict[str, Any],
    fn_hook_parameters_list: list[ToolParameterTypes],
    fn_pre_call_hook: PreToolCallHookProtocol | None,
    fn_post_call_hook: PostToolCallHookProtocol | None,
) -> Callable[..., Awaitable[list[TextContent | ImageContent | EmbeddedResource]]]:
    """Factory function to create the transformed tool's core async callable."""

    async def transformed_fn(
        **kwargs: Any,
    ) -> list[TextContent | ImageContent | EmbeddedResource]:
        try:
            validate(kwargs, fn_transformed_parameters_schema)
        except ValidationError as e:
            msg = f"Provided arguments for {e.json_path} are invalid: {e.message}"
            raise ToolError(msg) from e

        hook_args, tool_call_kwargs = _extract_hook_args(
            fn_hook_parameters_list, kwargs
        )

        if fn_pre_call_hook:
            await fn_pre_call_hook(tool_call_kwargs, hook_args)

        response = await original_tool_run_method(arguments=tool_call_kwargs)

        if fn_post_call_hook:
            await fn_post_call_hook(response, tool_call_kwargs, hook_args)

        return response

    return transformed_fn


def _transform_tool(
    tool: FastMCPTool,
    override: Annotated[ToolOverride, "Tool overrides for the tool."],
) -> FastMCPTool:
    transformed_parameters: dict[str, Any] = deepcopy(tool.parameters)

    transformed_parameters = _apply_hook_parameters(
        schema=transformed_parameters, hook_parameters=override.hook_parameters
    )
    transformed_parameters = _apply_parameter_overrides(
        schema=transformed_parameters, overrides=override.parameter_overrides
    )

    transformed_fn_callable = _create_transformed_function(
        original_tool_run_method=tool.run,
        fn_transformed_parameters_schema=transformed_parameters,
        fn_hook_parameters_list=override.hook_parameters,
        fn_pre_call_hook=override.pre_call_hook,
        fn_post_call_hook=override.post_call_hook,
    )

    transformed_name: str = override.name or tool.name
    transformed_description: str = override.description or tool.description

    return FastMCPTool(
        fn=transformed_fn_callable,
        name=transformed_name,
        description=transformed_description,
        parameters=transformed_parameters,
        tags=tool.tags,
        annotations=tool.annotations,
        serializer=tool.serializer,
    )


def transform_tool(
    tool: FastMCPTool,
    override: Annotated[ToolOverride, "Tool overrides for the tool."] | None = None,
    *,
    name: Annotated[str, "The name for the transformed tool."] | None = None,
    description: Annotated[str, "The description for the transformed tool."]
    | None = None,
    parameter_overrides: Annotated[
        list[ToolParameterTypes], "Parameter overrides for the tool."
    ]
    | None = None,
    hook_parameters: Annotated[
        list[ToolParameterTypes], "Hook parameters for the tool."
    ]
    | None = None,
    pre_call_hook: Annotated[
        PreToolCallHookProtocol | None,
        "A hook that is called before a tool call is made.",
    ] = None,
    post_call_hook: Annotated[
        PostToolCallHookProtocol | None,
        "A hook that is called after a tool call is made.",
    ] = None,
) -> FastMCPTool:
    """
    Transforms a tool with the given overrides.

    Args:
        tool: The tool to transform.
        override: The overrides to apply to the tool. If not provided, the name, description, parameter_overrides,
                  hook_parameters, pre_call_hook, and post_call_hook will be used.
        name: The name for the transformed tool.
        description: The description for the transformed tool.
        parameter_overrides: The parameter overrides to apply to the tool.
        hook_parameters: The hook parameters to apply to the tool.
        pre_call_hook: The pre-call hook to apply to the tool.
        post_call_hook: The post-call hook to apply to the tool.

    Returns:
        The transformed tool.

    Examples:
        >>> transform_tool(
        ...     tool=Tool(
        ...         name="my_tool",
        ...         description="This is my tool",
        ...         parameters={"arg1": "string"},
        ...     ),
        ...     name="my_tool_with_overrides",
        ...     description="This is my tool with overrides",
        ...     parameter_overrides=[
        ...         ToolParameter(
        ...             name="arg1",
        ...             description="now it has a description",
        ...             default="now it has a default value",
        ...         ),
        ...     ],
        ... )
    """

    if not override:
        override = ToolOverride(
            name=name,
            description=description,
            parameter_overrides=parameter_overrides or [],
            hook_parameters=hook_parameters or [],
            pre_call_hook=pre_call_hook,
            post_call_hook=post_call_hook,
        )

    return _transform_tool(tool, override)


def _add_transformed_tool_to_server(
    server: FastMCP,
    tool: FastMCPTool,
) -> None:
    """
    Adds a transformed tool to a server.
    """
    server._tool_manager.add_tool(tool)


def proxy_tool(
    tool: FastMCPTool,
    server: FastMCP,
    override: Annotated[ToolOverride, "Tool overrides for the tool."] | None = None,
    *,
    name: Annotated[str, "The name for the transformed tool."] | None = None,
    description: Annotated[str, "The description for the transformed tool."]
    | None = None,
    parameter_overrides: Annotated[
        list[ToolParameterTypes], "Parameter overrides for the tool."
    ]
    | None = None,
    hook_parameters: Annotated[
        list[ToolParameterTypes], "Hook parameters for the tool."
    ]
    | None = None,
    pre_call_hook: Annotated[
        PreToolCallHookProtocol | None,
        "A hook that is called before a tool call is made.",
    ] = None,
    post_call_hook: Annotated[
        PostToolCallHookProtocol | None,
        "A hook that is called after a tool call is made.",
    ] = None,
) -> FastMCPTool:
    """
    Transforms a tool with the given overrides and adds it to the target server.

    Args:
        tool: The tool to proxy.
        override: The overrides to apply to the tool.
        server: The server to proxy the tool to.
        name: The name for the transformed tool.
        description: The description for the transformed tool.
        parameter_overrides: The parameter overrides to apply to the tool.
        hook_parameters: The hook parameters to apply to the tool.
        pre_call_hook: The pre-call hook to apply to the tool.
        post_call_hook: The post-call hook to apply to the tool.

    Returns:
        The transformed tool.
    """

    if not override:
        override = ToolOverride(
            name=name,
            description=description,
            parameter_overrides=parameter_overrides or [],
            hook_parameters=hook_parameters or [],
            pre_call_hook=pre_call_hook,
            post_call_hook=post_call_hook,
        )

    transformed_tool = _transform_tool(tool, override)
    _add_transformed_tool_to_server(server, transformed_tool)
    return transformed_tool
