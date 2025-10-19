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

from fastmcp.server.context import Context
from fastmcp.tools.tool import Tool


async def list_resources(ctx: Context) -> list[dict[str, Any]]:
    """List all available resources on this server.

    Returns a list of resources with their URI, name, description, and MIME type.
    """
    resources = await ctx.fastmcp.get_resources()
    return [
        {
            "uri": resource.uri,
            "name": resource.name,
            "description": resource.description,
            "mimeType": resource.mime_type,
        }
        for resource in resources.values()
    ]


async def get_resource(uri: str, ctx: Context) -> dict[str, Any]:
    """Read a resource by its URI.

    Args:
        uri: The URI of the resource to read

    Returns:
        A dictionary containing the resource content and metadata
    """
    contents = await ctx.read_resource(uri)

    # Return first content block if single, all if multiple
    if len(contents) == 1:
        content = contents[0]
        result: dict[str, Any] = {
            "uri": uri,
            "mimeType": content.mime_type or "text/plain",
        }
        # ReadResourceContents has a 'content' attribute (str or bytes)
        if isinstance(content.content, str):
            result["text"] = content.content
        else:
            result["blob"] = content.content
        return result

    return {
        "uri": uri,
        "contents": [
            {
                "mimeType": c.mime_type or "text/plain",
                "text": c.content if isinstance(c.content, str) else None,
                "blob": c.content if isinstance(c.content, bytes) else None,
            }
            for c in contents
        ],
    }


async def list_prompts(ctx: Context) -> list[dict[str, Any]]:
    """List all available prompts on this server.

    Returns a list of prompts with their name, description, and arguments.
    """
    prompts = await ctx.fastmcp.get_prompts()
    return [
        {
            "name": prompt.name,
            "description": prompt.description,
            "arguments": [
                {
                    "name": arg.name,
                    "description": arg.description,
                    "required": arg.required,
                }
                for arg in (prompt.arguments or [])
            ],
        }
        for prompt in prompts.values()
    ]


async def get_prompt(
    name: str, arguments: dict[str, Any] | None = None, ctx: Context | None = None
) -> dict[str, Any]:
    """Get a prompt by name with optional arguments.

    Args:
        name: The name of the prompt to retrieve
        arguments: Optional dictionary of arguments to pass to the prompt

    Returns:
        A dictionary containing the prompt messages and metadata
    """
    if ctx is None:
        raise ValueError("Context is required for get_prompt")

    result = await ctx.fastmcp._get_prompt_mcp(name, arguments)
    return {
        "name": name,
        "description": result.description,
        "messages": [
            {
                "role": msg.role,
                "content": (
                    msg.content.text
                    if hasattr(msg.content, "text")
                    else str(msg.content)
                ),
            }
            for msg in result.messages
        ],
    }


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
