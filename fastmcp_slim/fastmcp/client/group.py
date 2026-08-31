"""Coordination of independent MCP client connections."""

from __future__ import annotations

import contextlib
import datetime
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType, TracebackType
from typing import Any

import anyio
import mcp_types
from mcp.client.caching import CacheMode

from fastmcp.client.client import CallToolResult, Client, ConnectMode
from fastmcp.client.logging import LogMessage
from fastmcp.client.progress import ProgressHandler
from fastmcp.mcp_config import MCPConfig
from fastmcp.utilities.async_utils import gather


@dataclass(frozen=True)
class GroupCallbackContext:
    """Provenance for a payload delivered through a group-level handler.

    ``server_name`` is the group's name for the member client that produced
    the payload. ``tool_name`` is the upstream tool name when the payload is
    call-scoped (progress); connection-scoped payloads (logs, protocol
    messages) carry ``None``.
    """

    server_name: str
    tool_name: str | None = None


GroupLogHandler = Callable[[LogMessage, GroupCallbackContext], Awaitable[None]]
"""Group-level log handler: ``(message, context) -> None``."""

GroupMessageHandler = Callable[
    ["mcp_types.ServerNotification | Exception", GroupCallbackContext],
    Awaitable[None],
]
"""Group-level protocol-message handler: ``(message, context) -> None``."""

GroupProgressHandler = Callable[
    [float, "float | None", "str | None", GroupCallbackContext],
    Awaitable[None],
]
"""Group-level progress handler: ``(progress, total, message, context) -> None``."""


def _bind_log_handler(
    handler: GroupLogHandler, context: GroupCallbackContext
) -> Callable[[LogMessage], Awaitable[None]]:
    async def bound(message: LogMessage) -> None:
        await handler(message, context)

    return bound


def _bind_message_handler(
    handler: GroupMessageHandler, context: GroupCallbackContext
) -> Callable[[Any], Awaitable[None]]:
    async def bound(message: Any) -> None:
        await handler(message, context)

    return bound


@dataclass(frozen=True)
class ToolRoute:
    """The client and upstream name behind a public group tool name."""

    server_name: str
    client: Client[Any]
    upstream_name: str


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
        progress_handler: GroupProgressHandler | None = None,
    ) -> None:
        if not clients:
            raise ValueError("ClientGroup requires at least one client")

        self._clients = dict(clients)
        self._progress_handler = progress_handler
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self._tool_routes: dict[str, ToolRoute] = {}
        self._catalog_loaded = False
        self._route_lock = anyio.Lock()

    @property
    def clients(self) -> Mapping[str, Client[Any]]:
        """The group's clients, keyed by server name.

        Read-only: membership is fixed at construction, since discovered routes
        hold the client that advertised each tool and would silently go stale
        if the mapping were swapped underneath them.
        """
        return MappingProxyType(self._clients)

    @classmethod
    def from_config(
        cls,
        config: MCPConfig | dict[str, Any],
        *,
        default_mode: ConnectMode = "auto",
        log_handler: GroupLogHandler | None = None,
        message_handler: GroupMessageHandler | None = None,
        progress_handler: GroupProgressHandler | None = None,
    ) -> ClientGroup:
        """Create one independent client for each configured server.

        A server entry may include a FastMCP-specific ``mode`` field. It applies
        only to that server; entries without one use ``default_mode``.

        Group-level handlers receive each payload together with a
        `GroupCallbackContext` naming the member that produced it, so one
        shared handler can tell servers apart:

        ```python
        async def log_handler(message: LogMessage, context: GroupCallbackContext):
            print(f"[{context.server_name}] {message.data.get('msg')}")

        group = ClientGroup.from_config(config, log_handler=log_handler)
        ```

        ``log_handler`` and ``message_handler`` are connection-scoped, so they
        can only be bound here, where the group constructs the member clients;
        a group built from explicit clients binds those at `Client(...)`
        construction instead. ``progress_handler`` is call-scoped and works on
        every group — it is forwarded to the constructor.
        """
        parsed = (
            config if isinstance(config, MCPConfig) else MCPConfig.from_dict(config)
        )
        clients: dict[str, Client[Any]] = {}

        for name, server in parsed.mcpServers.items():
            configured_mode = (server.model_extra or {}).get("mode", default_mode)
            if not isinstance(configured_mode, str):
                raise TypeError(f"Protocol mode for server {name!r} must be a string")

            client_kwargs: dict[str, Any] = {}
            context = GroupCallbackContext(server_name=name)
            if log_handler is not None:
                client_kwargs["log_handler"] = _bind_log_handler(log_handler, context)
            if message_handler is not None:
                client_kwargs["message_handler"] = _bind_message_handler(
                    message_handler, context
                )
            clients[name] = Client(
                server.to_transport(), mode=configured_mode, **client_kwargs
            )

        return cls(clients, progress_handler=progress_handler)

    @property
    def protocol_versions(self) -> dict[str, str | None]:
        return {name: client.protocol_version for name, client in self._clients.items()}

    async def __aenter__(self) -> ClientGroup:
        if self._exit_stack is not None:
            raise RuntimeError("ClientGroup is already connected")

        # Claim the stack before the first await so a concurrent entry hits the
        # guard above instead of racing past it and overwriting this one.
        stack = contextlib.AsyncExitStack()
        self._exit_stack = stack
        await stack.__aenter__()

        # Connect concurrently: entry latency stays one handshake deep instead
        # of growing linearly with the number of servers. With
        # return_exceptions=True every connection attempt runs to completion,
        # so on partial failure the successes are known and can be unwound.
        clients = list(self._clients.values())
        results = await gather(
            (client.__aenter__() for client in clients), return_exceptions=True
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            for client, result in zip(clients, results, strict=True):
                if not isinstance(result, BaseException):
                    with contextlib.suppress(Exception):
                        await client.__aexit__(None, None, None)
            self._exit_stack = None
            await stack.aclose()
            raise errors[0]

        for client in clients:
            stack.push_async_exit(client)

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
            name for name, client in self._clients.items() if not client.is_connected()
        ]
        if disconnected:
            names = ", ".join(repr(name) for name in disconnected)
            raise RuntimeError(f"ClientGroup clients are not connected: {names}")

    def _route_progress_handler(
        self, route: ToolRoute, explicit: ProgressHandler | None
    ) -> ProgressHandler | None:
        """Contextualize the group progress handler for one routed call.

        An explicit per-call handler wins; otherwise the group-level handler is
        bound to this call's provenance. Returns None when neither is set.
        """
        if explicit is not None:
            return explicit
        group_handler = self._progress_handler
        if group_handler is None:
            return None
        context = GroupCallbackContext(
            server_name=route.server_name, tool_name=route.upstream_name
        )

        async def handler(
            progress: float, total: float | None, message: str | None
        ) -> None:
            await group_handler(progress, total, message, context)

        return handler

    def _require_route_connected(self, route: ToolRoute) -> None:
        if not route.client.is_connected():
            raise RuntimeError(
                f"ClientGroup client for server {route.server_name!r} is not connected"
            )

    async def list_tools(
        self, *, cache_mode: CacheMode = "refresh"
    ) -> list[mcp_types.Tool]:
        """List tools from every client with namespaced names.

        An explicit call is the group's catalog-refresh mechanism, so it
        defaults to `cache_mode="refresh"`: a client-side response cache
        (SEP-2549) is repopulated rather than served, and the routes reflect
        what every server advertises now. Pass `cache_mode="use"` to allow
        cache hits when staleness within the server's hint is acceptable.
        """
        self._require_connected()
        tools: list[mcp_types.Tool] = []
        routes: dict[str, ToolRoute] = {}
        clients = list(self._clients.items())
        tool_lists = await gather(
            client.list_tools(cache_mode=cache_mode) for _, client in clients
        )

        for (server_name, client), server_tools in zip(
            clients, tool_lists, strict=True
        ):
            for tool in server_tools:
                public_name = f"{server_name}_{tool.name}"
                if public_name in routes:
                    raise ValueError(f"Tool name collision: {public_name!r}")
                routes[public_name] = ToolRoute(
                    server_name=server_name,
                    client=client,
                    upstream_name=tool.name,
                )
                tools.append(tool.model_copy(update={"name": public_name}))

        self._tool_routes = routes
        self._catalog_loaded = True
        return tools

    async def resolve_tool(self, name: str) -> ToolRoute:
        """Resolve a public tool name to its client and upstream identity.

        A known route only requires its own client to be connected; one dead
        server does not couple failures onto calls routed to healthy servers.
        Loading the catalog (the first resolution, or after a refresh) still
        requires every client, since discovery queries them all.
        """
        route = self._tool_routes.get(name)
        if route is not None:
            self._require_route_connected(route)
            return route
        if self._catalog_loaded:
            raise KeyError(
                f"Unknown tool: {name!r}. If servers changed their tools,"
                " call list_tools() to refresh the catalog."
            )

        async with self._route_lock:
            route = self._tool_routes.get(name)
            if route is not None:
                return route
            if not self._catalog_loaded:
                # Lazy cold-start discovery may serve a cached listing; only an
                # explicit list_tools() call promises a refreshed catalog.
                await self.list_tools(cache_mode="use")
                route = self._tool_routes.get(name)

        if route is None:
            raise KeyError(
                f"Unknown tool: {name!r}. If servers changed their tools,"
                " call list_tools() to refresh the catalog."
            )
        return route

    async def call_tool_mcp(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: datetime.timedelta | float | int | None = None,
        progress_handler: ProgressHandler | None = None,
        meta: dict[str, Any] | None = None,
    ) -> mcp_types.CallToolResult:
        """Call a namespaced tool and return its raw MCP result."""
        route = await self.resolve_tool(name)
        return await route.client.call_tool_mcp(
            route.upstream_name,
            arguments or {},
            timeout=timeout,
            progress_handler=self._route_progress_handler(route, progress_handler),
            meta=meta,
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        version: str | None = None,
        timeout: datetime.timedelta | float | int | None = None,
        progress_handler: ProgressHandler | None = None,
        raise_on_error: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Call a namespaced tool through the client that advertised it."""
        route = await self.resolve_tool(name)
        return await route.client.call_tool(
            route.upstream_name,
            arguments,
            version=version,
            timeout=timeout,
            progress_handler=self._route_progress_handler(route, progress_handler),
            raise_on_error=raise_on_error,
            meta=meta,
        )
