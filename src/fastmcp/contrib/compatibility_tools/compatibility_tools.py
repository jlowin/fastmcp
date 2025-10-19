"""Compatibility tools for clients that only support tools capability.

This module provides four standalone tools that expose resources and prompts
as callable tools for clients that cannot access them through native MCP endpoints.

Usage:
    ```python
    from fastmcp import FastMCP
    from fastmcp.contrib.compatibility_tools import (
        list_resources_tool,
        get_resource_tool,
        list_prompts_tool,
        get_prompt_tool,
        add_compatibility_tools,
    )

    mcp = FastMCP("My Server")

    # Add individual tools
    mcp.add_tool(list_resources_tool)
    mcp.add_tool(get_resource_tool)

    # Or add all at once
    add_compatibility_tools(mcp)
    ```
"""

from __future__ import annotations

from typing import Any

import mcp.types

from fastmcp.server.context import Context
from fastmcp.tools.tool import Tool


async def list_resources(ctx: Context) -> mcp.types.ListResourcesResult:
    """List all available resources on this server.

    Returns the raw MCP protocol ListResourcesResult object.
    """
    resources = await ctx.fastmcp._list_resources_mcp()
    return mcp.types.ListResourcesResult(resources=resources)


async def get_resource(uri: str, ctx: Context) -> mcp.types.ReadResourceResult:
    """Read a resource by its URI.

    Args:
        uri: The URI of the resource to read

    Returns:
        The raw MCP protocol ReadResourceResult object.
    """
    contents = await ctx.fastmcp._read_resource_mcp(uri)
    # Convert ReadResourceContents to proper MCP types
    mcp_contents: list[
        mcp.types.TextResourceContents | mcp.types.BlobResourceContents
    ] = [
        mcp.types.TextResourceContents(
            uri=uri,  # type: ignore[arg-type]
            mimeType=c.mime_type,
            text=c.content,  # type: ignore[arg-type]
        )
        if isinstance(c.content, str)
        else mcp.types.BlobResourceContents(
            uri=uri,  # type: ignore[arg-type]
            mimeType=c.mime_type,
            blob=c.content,  # type: ignore[arg-type]
        )
        for c in contents
    ]
    return mcp.types.ReadResourceResult(contents=mcp_contents)


async def list_prompts(ctx: Context) -> mcp.types.ListPromptsResult:
    """List all available prompts on this server.

    Returns the raw MCP protocol ListPromptsResult object.
    """
    prompts = await ctx.fastmcp._list_prompts_mcp()
    return mcp.types.ListPromptsResult(prompts=prompts)


async def get_prompt(
    name: str, arguments: dict[str, Any] | None = None, ctx: Context | None = None
) -> mcp.types.GetPromptResult:
    """Get a prompt by name with optional arguments.

    Args:
        name: The name of the prompt to retrieve
        arguments: Optional dictionary of arguments to pass to the prompt

    Returns:
        The raw MCP protocol GetPromptResult object.
    """
    if ctx is None:
        raise ValueError("Context is required for get_prompt")

    return await ctx.fastmcp._get_prompt_mcp(name, arguments)


# Create Tool instances from functions
# Note: We set output_schema=None to avoid automatic wrapping of results
# This makes the tools simpler and more predictable for clients
list_resources_tool = Tool.from_function(
    list_resources,
    name="list_resources",
    description="List all available resources on this server",
    output_schema=None,
)

get_resource_tool = Tool.from_function(
    get_resource,
    name="get_resource",
    description="Read a resource by its URI",
    output_schema=None,
)

list_prompts_tool = Tool.from_function(
    list_prompts,
    name="list_prompts",
    description="List all available prompts on this server",
    output_schema=None,
)

get_prompt_tool = Tool.from_function(
    get_prompt,
    name="get_prompt",
    description="Get a prompt by name with optional arguments",
    output_schema=None,
)


def add_compatibility_tools(mcp: Any) -> None:
    """Add all compatibility tools to a FastMCP server.

    Args:
        mcp: The FastMCP server instance to add tools to

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.contrib.compatibility_tools import add_compatibility_tools

        mcp = FastMCP("My Server")
        add_compatibility_tools(mcp)
        ```
    """
    mcp.add_tool(list_resources_tool)
    mcp.add_tool(get_resource_tool)
    mcp.add_tool(list_prompts_tool)
    mcp.add_tool(get_prompt_tool)
