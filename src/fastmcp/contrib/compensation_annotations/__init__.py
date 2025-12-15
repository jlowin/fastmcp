"""Compensation annotation discovery for MCP tools.

This module provides utilities to discover compensation pairs from MCP tool schemas
using the `x-compensation-pair` annotation convention. Compensation pairs define
relationships between tools that create resources and tools that undo those creations.

Example:
    >>> from fastmcp import FastMCP
    >>> from fastmcp.contrib.compensation_annotations import discover_compensation_pairs
    >>>
    >>> mcp = FastMCP("MyServer")
    >>>
    >>> @mcp.tool(annotations={"x-compensation-pair": "delete_item"})
    ... def add_item(name: str) -> dict:
    ...     return {"id": "123", "name": name}
    >>>
    >>> @mcp.tool
    ... def delete_item(item_id: str) -> dict:
    ...     return {"deleted": item_id}
    >>>
    >>> # Discover compensation pairs from tool schemas
    >>> pairs = discover_compensation_pairs(mcp._tool_manager.tools.values())
    >>> # Returns: {"add_item": "delete_item"}

Supported annotation locations:
    - `annotations["x-compensation-pair"]` (recommended)
    - `inputSchema["x-compensation-pair"]`
    - Top-level schema `x-compensation-pair`
"""

from fastmcp.contrib.compensation_annotations.parser import (
    discover_compensation_pairs,
    parse_mcp_schema,
    validate_mcp_schema,
)

__all__ = [
    "discover_compensation_pairs",
    "parse_mcp_schema",
    "validate_mcp_schema",
]
