from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import ConfigDict

from fastmcp import Client, Context, FastMCP
from fastmcp.client.transports import FastMCPTransport
from fastmcp.experimental.client_group import ClientGroup
from fastmcp.mcp_config import MCPConfig, StdioMCPServer


class LegacyFastMCPTransport(FastMCPTransport):
    legacy_only = True


class InMemoryServer(StdioMCPServer):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    mcp: FastMCP
    command: str = "in-memory"

    def to_transport(self) -> FastMCPTransport:
        return FastMCPTransport(self.mcp)


class LegacyInMemoryServer(InMemoryServer):
    def to_transport(self) -> FastMCPTransport:
        return LegacyFastMCPTransport(self.mcp)


def make_server(name: str) -> FastMCP:
    server = FastMCP(name)

    @server.tool
    async def protocol_era(ctx: Context) -> str:
        request_context = ctx.request_context
        assert request_context is not None
        return request_context.protocol_version

    @server.tool
    def echo(value: str) -> str:
        return f"{name}: {value}"

    return server


async def test_clients_negotiate_independently():
    legacy = Client(LegacyFastMCPTransport(make_server("legacy")))
    modern = Client(FastMCPTransport(make_server("modern")))
    group = ClientGroup({"old": legacy, "new": modern})

    async with group:
        assert group.protocol_versions == {
            "old": "2025-11-25",
            "new": "2026-07-28",
        }

        tools = await group.list_tools()
        assert {tool.name for tool in tools} == {
            "old_protocol_era",
            "old_echo",
            "new_protocol_era",
            "new_echo",
        }

        old_era = await group.call_tool("old_protocol_era")
        new_era = await group.call_tool("new_protocol_era")
        echoed = await group.call_tool("new_echo", {"value": "hello"})

        assert old_era.data == "2025-11-25"
        assert new_era.data == "2026-07-28"
        assert echoed.data == "modern: hello"

    assert not legacy.is_connected()
    assert not modern.is_connected()


async def test_from_config_applies_mode_per_server():
    config = MCPConfig(
        mcpServers={
            "old": InMemoryServer(mcp=make_server("old"), mode="legacy"),
            "new": InMemoryServer(mcp=make_server("new"), mode="auto"),
        }
    )
    group = ClientGroup.from_config(config)

    async with group:
        assert group.protocol_versions == {
            "old": "2025-11-25",
            "new": "2026-07-28",
        }


async def test_call_tool_populates_routes_lazily():
    group = ClientGroup({"server": Client(make_server("server"))})

    async with group:
        result = await group.call_tool("server_echo", {"value": "hello"})

    assert result.data == "server: hello"


async def test_callers_can_manage_connections():
    old = Client(LegacyFastMCPTransport(make_server("old")))
    new = Client(FastMCPTransport(make_server("new")))
    group = ClientGroup({"old": old, "new": new})

    async with old, new:
        tools = await group.list_tools()
        result = await group.call_tool("new_echo", {"value": "hello"})

        assert {tool.name for tool in tools} >= {"old_echo", "new_echo"}
        assert result.data == "new: hello"
        assert group.protocol_versions == {
            "old": "2025-11-25",
            "new": "2026-07-28",
        }

    assert not old.is_connected()
    assert not new.is_connected()


async def test_group_context_does_not_close_caller_owned_client():
    client = Client(make_server("server"))
    group = ClientGroup({"server": client})

    async with client:
        async with group:
            result = await group.call_tool("server_echo", {"value": "hello"})
            assert result.data == "server: hello"

        assert client.is_connected()

    assert not client.is_connected()


async def test_group_requires_each_client_to_be_connected():
    connected = Client(make_server("connected"))
    disconnected = Client(make_server("disconnected"))
    group = ClientGroup({"connected": connected, "disconnected": disconnected})

    async with connected:
        try:
            await group.list_tools()
        except RuntimeError as exc:
            assert str(exc) == "ClientGroup clients are not connected: 'disconnected'"
        else:
            raise AssertionError("Expected a disconnected-client error")


async def test_group_keeps_one_connection_per_server():
    lifecycles = {"entered": 0, "exited": 0}

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        lifecycles["entered"] += 1
        try:
            yield {}
        finally:
            lifecycles["exited"] += 1

    server = FastMCP("stateful", lifespan=lifespan)

    @server.tool
    def echo(value: str) -> str:
        return value

    group = ClientGroup({"stateful": Client(server)})
    async with group:
        await group.list_tools()
        await group.call_tool("stateful_echo", {"value": "one"})
        await group.call_tool("stateful_echo", {"value": "two"})
        assert lifecycles == {"entered": 1, "exited": 0}

    assert lifecycles == {"entered": 1, "exited": 1}


async def test_tool_name_collisions_are_rejected():
    group = ClientGroup(
        {
            "one": Client(make_server("one")),
            "two": Client(make_server("two")),
        },
        tool_name_fn=lambda _server, tool: tool,
    )

    async with group:
        try:
            await group.list_tools()
        except ValueError as exc:
            assert str(exc) == "Tool name collision: 'protocol_era'"
        else:
            raise AssertionError("Expected a tool name collision")
