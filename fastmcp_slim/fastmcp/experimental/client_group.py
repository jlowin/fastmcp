"""Experimental coordination of independent MCP client connections."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import anyio
import mcp_types

from fastmcp.client.client import CallToolResult, Client, ConnectMode
from fastmcp.client.progress import ProgressHandler
from fastmcp.mcp_config import MCPConfig
from fastmcp.utilities.async_utils import gather


class ClientGroup:
    """Coordinate independent clients without introducing a proxy server.

    Each client retains its own transport, session, capabilities, and protocol
    version. The group only combines tool discovery and routes tool calls.

    Callers may manage the clients' connections themselves or use the group as
    a convenience context manager. Entering an already-connected FastMCP client
    is safe because client contexts are reference counted.
    """

    def __init__(self, clients: Mapping[str, Client[Any]]) -> None:
        if not clients:
            raise ValueError("ClientGroup requires at least one client")

        self.clients = dict(clients)
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self._tool_routes: dict[str, tuple[Client[Any], str]] = {}
        self._catalog_loaded = False
        self._route_lock = anyio.Lock()

    @classmethod
    def from_config(
        cls,
        config: MCPConfig | dict[str, Any],
        *,
        default_mode: ConnectMode = "auto",
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

        return cls(clients)

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
        self._catalog_loaded = False
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
        clients = list(self.clients.items())
        tool_lists = await gather(client.list_tools() for _, client in clients)

        for (server_name, client), server_tools in zip(
            clients, tool_lists, strict=True
        ):
            for tool in server_tools:
                public_name = f"{server_name}_{tool.name}"
                if public_name in routes:
                    raise ValueError(f"Tool name collision: {public_name!r}")
                routes[public_name] = (client, tool.name)
                tools.append(tool.model_copy(update={"name": public_name}))

        self._tool_routes = routes
        self._catalog_loaded = True
        return tools

    async def _resolve_tool(self, name: str) -> tuple[Client[Any], str]:
        self._require_connected()
        route = self._tool_routes.get(name)
        if route is not None:
            return route
        if self._catalog_loaded:
            raise KeyError(f"Unknown tool: {name!r}")

        async with self._route_lock:
            route = self._tool_routes.get(name)
            if route is not None:
                return route
            if not self._catalog_loaded:
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
