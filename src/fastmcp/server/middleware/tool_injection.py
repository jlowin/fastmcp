"""A middleware for response caching."""

from collections.abc import Sequence
from logging import Logger
from typing import Annotated, Any

import mcp.types
from mcp.types import Prompt
from pydantic import AnyUrl
from typing_extensions import override

from fastmcp.client.client import Client
from fastmcp.client.transports import FastMCPTransport
from fastmcp.server.context import Context
from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import Tool, ToolResult
from fastmcp.utilities.logging import get_logger

logger: Logger = get_logger(name=__name__)


class ToolInjectionMiddleware(Middleware):
    """A middleware for injecting tools into the context."""

    def __init__(self, tools: Sequence[Tool]):
        """Initialize the tool injection middleware."""
        self._tools_to_inject: Sequence[Tool] = tools
        self._tools_to_inject_by_name: dict[str, Tool] = {
            tool.name: tool for tool in tools
        }

    @override
    async def on_list_tools(
        self,
        context: MiddlewareContext[mcp.types.ListToolsRequest],
        call_next: CallNext[mcp.types.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """Inject tools into the response."""
        return [*self._tools_to_inject, *await call_next(context)]

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mcp.types.CallToolRequestParams],
        call_next: CallNext[mcp.types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls to injected tools."""
        if context.message.name in self._tools_to_inject_by_name:
            tool = self._tools_to_inject_by_name[context.message.name]
            return await tool.run(arguments=context.message.arguments or {})

        return await call_next(context)


async def list_prompts(context: Context) -> list[Prompt]:
    """List prompts available on the server."""

    async with Client[FastMCPTransport](context.fastmcp) as client:
        return await client.list_prompts()


list_prompts_tool = Tool.from_function(
    fn=list_prompts,
)


async def render_prompt(
    context: Context,
    name: Annotated[str, "The name of the prompt to render."],
    arguments: Annotated[dict[str, Any], "The arguments to pass to the prompt."],
) -> mcp.types.GetPromptResult:
    """Render a prompt available on the server."""

    async with Client[FastMCPTransport](context.fastmcp) as client:
        return await client.get_prompt(name=name, arguments=arguments)


render_prompt_tool = Tool.from_function(
    fn=render_prompt,
)


async def list_resources(context: Context) -> list[mcp.types.Resource]:
    """List resources available on the server."""

    async with Client[FastMCPTransport](context.fastmcp) as client:
        return await client.list_resources()


list_resources_tool = Tool.from_function(
    fn=list_resources,
)


async def read_resource(
    context: Context,
    uri: Annotated[AnyUrl | str, "The URI of the resource to read."],
) -> list[mcp.types.TextResourceContents | mcp.types.BlobResourceContents]:
    """Read a resource available on the server."""

    async with Client[FastMCPTransport](context.fastmcp) as client:
        return await client.read_resource(uri=uri)


read_resource_tool = Tool.from_function(
    fn=read_resource,
)


class PromptToolMiddleware(Middleware):
    """A middleware for injecting prompts as tools into the context."""

    def __init__(self) -> None:
        super().__init__()

    @override
    async def on_list_tools(
        self,
        context: MiddlewareContext[mcp.types.ListToolsRequest],
        call_next: CallNext[mcp.types.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """Inject prompts as tools into the response."""
        return [*await call_next(context), list_prompts_tool, render_prompt_tool]

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mcp.types.CallToolRequestParams],
        call_next: CallNext[mcp.types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls to injected tools."""
        if context.message.name == render_prompt_tool.name:
            return await render_prompt_tool.run(
                arguments=context.message.arguments or {}
            )

        if context.message.name == list_prompts_tool.name:
            return await list_prompts_tool.run(
                arguments=context.message.arguments or {}
            )

        return await call_next(context)


class ResourceToolMiddleware(Middleware):
    """A middleware for injecting resources as tools into the context."""

    def __init__(self) -> None:
        super().__init__()

    @override
    async def on_list_tools(
        self,
        context: MiddlewareContext[mcp.types.ListToolsRequest],
        call_next: CallNext[mcp.types.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """Inject resources as tools into the response."""
        return [*await call_next(context), list_resources_tool, read_resource_tool]

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mcp.types.CallToolRequestParams],
        call_next: CallNext[mcp.types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls to injected tools."""
        if context.message.name == list_resources_tool.name:
            return await list_resources_tool.run(
                arguments=context.message.arguments or {}
            )

        if context.message.name == read_resource_tool.name:
            return await read_resource_tool.run(
                arguments=context.message.arguments or {}
            )

        return await call_next(context)
