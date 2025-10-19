"""Compatibility tools for clients that only support tools capability."""

from fastmcp.contrib.compatibility_tools.compatibility_tools import (
    add_compatibility_tools,
    get_prompt_tool,
    get_resource_tool,
    list_prompts_tool,
    list_resources_tool,
)

__all__ = [
    "list_resources_tool",
    "get_resource_tool",
    "list_prompts_tool",
    "get_prompt_tool",
    "add_compatibility_tools",
]
