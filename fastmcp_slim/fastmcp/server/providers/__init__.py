"""Providers for dynamic MCP components.

This module provides the `Provider` abstraction for providing tools,
resources, and prompts dynamically at runtime.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.providers import Provider
    from fastmcp.tools import Tool

    class DatabaseProvider(Provider):
        def __init__(self, db_url: str):
            self.db = Database(db_url)

        async def _list_tools(self) -> list[Tool]:
            rows = await self.db.fetch("SELECT * FROM tools")
            return [self._make_tool(row) for row in rows]

        async def _get_tool(self, name: str) -> Tool | None:
            row = await self.db.fetchone("SELECT * FROM tools WHERE name = ?", name)
            return self._make_tool(row) if row else None

    mcp = FastMCP("Server", providers=[DatabaseProvider(db_url)])
    ```
"""

from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from fastmcp.server.providers.aggregate import (
        AggregateProvider as AggregateProvider,
    )
    from fastmcp.server.providers.base import Provider as Provider
    from fastmcp.server.providers.fastmcp_provider import (
        FastMCPProvider as FastMCPProvider,
    )
    from fastmcp.server.providers.filesystem import (
        FileSystemProvider as FileSystemProvider,
    )
    from fastmcp.server.providers.local_provider import LocalProvider as LocalProvider
    from fastmcp.server.providers.openapi import OpenAPIProvider as OpenAPIProvider
    from fastmcp.server.providers.proxy import ProxyProvider as ProxyProvider
    from fastmcp.server.providers.skills import (
        ClaudeSkillsProvider as ClaudeSkillsProvider,
    )
    from fastmcp.server.providers.skills import SkillProvider as SkillProvider
    from fastmcp.server.providers.skills import (
        SkillsDirectoryProvider as SkillsDirectoryProvider,
    )

__all__ = [
    "AggregateProvider",
    "ClaudeSkillsProvider",
    "FastMCPProvider",
    "FileSystemProvider",
    "LocalProvider",
    "OpenAPIProvider",
    "Provider",
    "ProxyProvider",
    "SkillProvider",
    "SkillsDirectoryProvider",
]

_LAZY_IMPORTS = {
    "AggregateProvider": ("fastmcp.server.providers.aggregate", "AggregateProvider"),
    "ClaudeSkillsProvider": (
        "fastmcp.server.providers.skills",
        "ClaudeSkillsProvider",
    ),
    "FastMCPProvider": (
        "fastmcp.server.providers.fastmcp_provider",
        "FastMCPProvider",
    ),
    "FileSystemProvider": (
        "fastmcp.server.providers.filesystem",
        "FileSystemProvider",
    ),
    "LocalProvider": ("fastmcp.server.providers.local_provider", "LocalProvider"),
    "OpenAPIProvider": ("fastmcp.server.providers.openapi", "OpenAPIProvider"),
    "Provider": ("fastmcp.server.providers.base", "Provider"),
    "ProxyProvider": ("fastmcp.server.providers.proxy", "ProxyProvider"),
    "SkillProvider": ("fastmcp.server.providers.skills", "SkillProvider"),
    "SkillsDirectoryProvider": (
        "fastmcp.server.providers.skills",
        "SkillsDirectoryProvider",
    ),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
