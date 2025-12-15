"""Providers for dynamic MCP components.

This module provides the `Provider` abstraction for providing tools,
resources, and prompts dynamically at runtime.

Example:
    ```python
    from fastmcp import FastMCP, Provider
    from fastmcp.server.context import Context
    from fastmcp.tools import Tool

    class DatabaseProvider(Provider):
        def __init__(self, db_url: str):
            self.db = Database(db_url)

        async def list_tools(self, context: Context) -> list[Tool]:
            rows = await self.db.fetch("SELECT * FROM tools")
            return [self._make_tool(row) for row in rows]

        async def get_tool(self, context: Context, name: str) -> Tool | None:
            row = await self.db.fetchone("SELECT * FROM tools WHERE name = ?", name)
            return self._make_tool(row) if row else None

    mcp = FastMCP("Server", providers=[DatabaseProvider(db_url)])
    ```
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from fastmcp.prompts.prompt import Prompt
from fastmcp.resources.resource import Resource
from fastmcp.tools.tool import Tool

if TYPE_CHECKING:
    from fastmcp.server.context import Context

__all__ = [
    "Provider",
]


class Provider:
    """Base class for dynamic component providers.

    Subclass and override whichever methods you need. Default implementations
    return empty lists / None, so you only need to implement what your provider
    supports.

    All provider methods receive the FastMCP Context, giving access to
    session info, logging, and other request-scoped capabilities.

    Provider semantics:
        - Return `None` from `get_*` methods to indicate "I don't have it" (search continues)
        - Raise an exception for actual errors (propagates to caller)
        - Static components (registered via decorators) always take precedence over providers
        - Providers are queried in registration order; first non-None wins
    """

    async def list_tools(self, context: Context) -> Sequence[Tool]:
        """Return all available tools.

        Override to provide tools dynamically.
        """
        return []

    async def get_tool(self, context: Context, name: str) -> Tool | None:
        """Get a specific tool by name.

        Default implementation lists all tools and finds by name.
        Override for more efficient single-tool lookup.

        Returns:
            The Tool if found, or None to continue searching other providers.
        """
        tools = await self.list_tools(context)
        return next((t for t in tools if t.name == name), None)

    async def list_resources(self, context: Context) -> Sequence[Resource]:
        """Return all available resources.

        Override to provide resources dynamically.
        """
        return []

    async def get_resource(self, context: Context, uri: str) -> Resource | None:
        """Get a specific resource by URI.

        Default implementation lists all resources and finds by URI.
        Override for more efficient single-resource lookup.

        Returns:
            The Resource if found, or None to continue searching other providers.
        """
        resources = await self.list_resources(context)
        return next((r for r in resources if str(r.uri) == uri), None)

    async def list_prompts(self, context: Context) -> Sequence[Prompt]:
        """Return all available prompts.

        Override to provide prompts dynamically.
        """
        return []

    async def get_prompt(self, context: Context, name: str) -> Prompt | None:
        """Get a specific prompt by name.

        Default implementation lists all prompts and finds by name.
        Override for more efficient single-prompt lookup.

        Returns:
            The Prompt if found, or None to continue searching other providers.
        """
        prompts = await self.list_prompts(context)
        return next((p for p in prompts if p.name == name), None)
