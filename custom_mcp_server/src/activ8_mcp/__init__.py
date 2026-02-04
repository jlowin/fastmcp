"""
Activ8-AI Custom MCP Server

A unified MCP infrastructure for the Activ8-AI organization.
Provides tools for system, files, git, search, http, text, network, and datetime operations.
"""

from activ8_mcp.server import mcp
from activ8_mcp.registry import (
    MCP_REGISTRY,
    MCPServer,
    ServerType,
    UseCase,
    get_enabled_servers,
    get_servers_by_use_case,
    check_server_secrets,
)

__version__ = "1.0.0"
__all__ = [
    "mcp",
    "MCP_REGISTRY",
    "MCPServer",
    "ServerType",
    "UseCase",
    "get_enabled_servers",
    "get_servers_by_use_case",
    "check_server_secrets",
]
