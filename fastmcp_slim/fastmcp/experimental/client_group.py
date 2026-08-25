"""Experimental coordination of independent MCP client connections."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any

import mcp_types

from fastmcp.client.client import CallToolResult, Client, ConnectMode
from fastmcp.client.progress import ProgressHandler
from fastmcp.mcp_config import MCPConfig

ToolNameFn = Callable[[str, str], str]


def _prefix_tool_name(server_name: str, tool_name: str) -> str:
    return f"{server_name}_{tool_name}"


class ClientGroup:
    """Coordinate independent clients without introducing a proxy server.

    Each client retains its own transport, session, capabilities, and protocol
    version. The group only combines tool discovery and routes tool calls.

    Callers may manage the clients' connections themselves or use the group as
    a convenience context manager. Entering an already-connected FastMCP client
    is safe because client contexts are reference counted.
    """

    def __init__(
        self,
        clients: Mapping[str, Client[Any]],
        *,
        tool_name_fn: ToolNameFn = _prefix_tool_name,
    ) -> None:
        if not clients:
            raise ValueError("ClientGroup requires at least one client")

        self.clients = dict(clients)
        self.tool_name_fn = tool_name_fn
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self._tool_routes: dict[str, tuple[Client[Any], str]] = {}

    @classmethod
    def from_config(
        cls,
        config: MCPConfig | dict[str, Any],
        *,
        default_mode: ConnectMode = "auto",
        tool_name_fn: ToolNameFn = _prefix_tool_name,
    ) -> ClientGroup:
        """Create one independent client for each configured server.

        A server entry may include a FastMCP-specific ``mode`` field. It applies
        only to that server; entries without one use ``default_mode``.
        """
        parsed = (
            config if isinstance(config, MCPConfig) else MCPConfig.from_dict(config)
        )
        clients: dict[str, Client[Any]] = {}

        for name, server in parsed.mcpServers.items():
            configured_mode = (server.model_extra or {}).get("mode", default_mode)
            if not isinstance(configured_mode, str):
                raise TypeError(f"Protocol mode for server {name!r} must be a string")
            clients[name] = Client(server.to_transport(), mode=configured_mode)

        return cls(clients, tool_name_fn=tool_name_fn)

    @property
    def protocol_versions(self) -> dict[str, str | None]:
        return {name: client.protocol_version for name, client in self.clients.items()}

    async def __aenter__(self) -> ClientGroup:
        if self._exit_stack is not None:
            raise RuntimeError("ClientGroup is already connected")

        stack = contextlib.AsyncExitStack()
        await stack.__aenter__()
        try:
            for client in self.clients.values():
                await stack.enter_async_context(client)
        except BaseException:
            await stack.aclose()
            raise

        self._exit_stack = stack
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        stack = self._exit_stack
        self._exit_stack = None
        self._tool_routes.clear()
        if stack is not None:
            return await stack.__aexit__(exc_type, exc_value, traceback)
        return None

    def _require_connected(self) -> None:
        disconnected = [
            name for name, client in self.clients.items() if not client.is_connected()
        ]
        if disconnected:
            names = ", ".join(repr(name) for name in disconnected)
            raise RuntimeError(f"ClientGroup clients are not connected: {names}")

    async def list_tools(self) -> list[mcp_types.Tool]:
        """List tools from every client with namespaced names."""
        self._require_connected()
        tools: list[mcp_types.Tool] = []
        routes: dict[str, tuple[Client[Any], str]] = {}

        for server_name, client in self.clients.items():
            for tool in await client.list_tools():
                public_name = self.tool_name_fn(server_name, tool.name)
                if public_name in routes:
                    raise ValueError(f"Tool name collision: {public_name!r}")
                routes[public_name] = (client, tool.name)
                tools.append(tool.model_copy(update={"name": public_name}))

        self._tool_routes = routes
        return tools

    async def _resolve_tool(self, name: str) -> tuple[Client[Any], str]:
        self._require_connected()
        route = self._tool_routes.get(name)
        if route is None:
            await self.list_tools()
            route = self._tool_routes.get(name)
        if route is None:
            raise KeyError(f"Unknown tool: {name!r}")
        return route

    async def call_tool_mcp(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | int | None = None,
        progress_handler: ProgressHandler | None = None,
        meta: dict[str, Any] | None = None,
    ) -> mcp_types.CallToolResult:
        """Call a namespaced tool and return its raw MCP result."""
        client, upstream_name = await self._resolve_tool(name)
        return await client.call_tool_mcp(
            upstream_name,
            arguments or {},
            timeout=timeout,
            progress_handler=progress_handler,
            meta=meta,
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        version: str | None = None,
        timeout: float | int | None = None,
        progress_handler: ProgressHandler | None = None,
        raise_on_error: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Call a namespaced tool through the client that advertised it."""
        client, upstream_name = await self._resolve_tool(name)
        return await client.call_tool(
            upstream_name,
            arguments,
            version=version,
            timeout=timeout,
            progress_handler=progress_handler,
            raise_on_error=raise_on_error,
            meta=meta,
        )
