import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ConfigDict

from fastmcp import Client, Context, FastMCP
from fastmcp.client.group import ClientGroup, GroupCallbackContext
from fastmcp.client.transports import FastMCPTransport
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
        route = await group.resolve_tool("new_echo")
        assert route.server_name == "new"
        assert route.client is modern
        assert route.upstream_name == "echo"

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


async def test_concurrent_cold_calls_share_tool_discovery():
    first = Client(make_server("first"))
    second = Client(make_server("second"))
    group = ClientGroup({"first": first, "second": second})

    with (
        patch.object(first, "list_tools", wraps=first.list_tools) as first_list,
        patch.object(second, "list_tools", wraps=second.list_tools) as second_list,
    ):
        async with group:
            results = await asyncio.gather(
                group.call_tool("first_echo", {"value": "one"}),
                group.call_tool("second_echo", {"value": "two"}),
                group.call_tool("first_protocol_era"),
            )

    assert [result.data for result in results] == [
        "first: one",
        "second: two",
        "2026-07-28",
    ]
    assert first_list.call_count == 1
    assert second_list.call_count == 1


async def test_unknown_tools_do_not_repeat_discovery():
    first = Client(make_server("first"))
    second = Client(make_server("second"))
    group = ClientGroup({"first": first, "second": second})

    with (
        patch.object(first, "list_tools", wraps=first.list_tools) as first_list,
        patch.object(second, "list_tools", wraps=second.list_tools) as second_list,
    ):
        async with group:
            for name in ("missing", "also_missing", "missing"):
                with pytest.raises(KeyError, match=f"Unknown tool: {name!r}"):
                    await group.call_tool(name)

    assert first_list.call_count == 1
    assert second_list.call_count == 1


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
    first = FastMCP("first")
    second = FastMCP("second")

    @first.tool(name="b_echo")
    def first_echo() -> str:
        return "first"

    @second.tool(name="echo")
    def second_echo() -> str:
        return "second"

    group = ClientGroup(
        {
            "a": Client(first),
            "a_b": Client(second),
        }
    )

    async with group:
        try:
            await group.list_tools()
        except ValueError as exc:
            assert str(exc) == "Tool name collision: 'a_b_echo'"
        else:
            raise AssertionError("Expected a tool name collision")


async def test_single_client_group_provides_namespacing_alone():
    group = ClientGroup({"solo": Client(FastMCPTransport(make_server("solo")))})

    async with group:
        tools = await group.list_tools()
        assert sorted(tool.name for tool in tools) == ["solo_echo", "solo_protocol_era"]

        result = await group.call_tool("solo_echo", {"value": "hi"})
        assert result.data == "solo: hi"


async def test_client_membership_is_immutable():
    group = ClientGroup({"solo": Client(FastMCPTransport(make_server("solo")))})

    with pytest.raises(TypeError):
        group.clients["other"] = Client(  # ty: ignore[invalid-assignment]
            FastMCPTransport(make_server("other"))
        )


async def test_concurrent_group_entry_does_not_double_connect():
    client = Client(FastMCPTransport(make_server("solo")))
    group = ClientGroup({"solo": client})

    results = await asyncio.gather(
        group.__aenter__(), group.__aenter__(), return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)

    await group.__aexit__(None, None, None)
    assert not client.is_connected()


async def test_known_route_survives_an_unrelated_dead_client():
    healthy = Client(FastMCPTransport(make_server("healthy")))
    doomed = Client(FastMCPTransport(make_server("doomed")))
    group = ClientGroup({"healthy": healthy, "doomed": doomed})

    async with healthy:
        async with doomed:
            await group.list_tools()
        assert not doomed.is_connected()

        result = await group.call_tool("healthy_echo", {"value": "hi"})
        assert result.data == "healthy: hi"

        with pytest.raises(RuntimeError, match="doomed"):
            await group.call_tool("doomed_echo", {"value": "hi"})


async def test_partial_connect_failure_unwinds_connected_clients():
    ok = Client(FastMCPTransport(make_server("ok")))
    bad = Client(FastMCPTransport(make_server("bad")))
    group = ClientGroup({"ok": ok, "bad": bad})

    from unittest.mock import AsyncMock

    with patch.object(bad, "__aenter__", AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError, match="boom"):
            async with group:
                pass

    assert not ok.is_connected()
    assert group._exit_stack is None


async def test_explicit_list_tools_refreshes_past_client_response_cache():
    """A cache-hinted server must not leave group.list_tools() serving a stale
    catalog: the explicit call is the documented refresh mechanism."""
    server = FastMCP("hinted", cache_ttl=60000)

    @server.tool
    def original() -> str:
        return "original"

    client = Client(FastMCPTransport(server), cache=True)
    group = ClientGroup({"hinted": client})

    async with group:
        tools = await group.list_tools()
        assert [tool.name for tool in tools] == ["hinted_original"]

        @server.tool
        def added() -> str:
            return "added"

        refreshed = await group.list_tools()
        assert {tool.name for tool in refreshed} == {"hinted_original", "hinted_added"}

        result = await group.call_tool("hinted_added")
        assert result.data == "added"


async def test_from_config_log_handler_receives_provenance():
    def make_logging_server(name: str) -> FastMCP:
        server = FastMCP(name)

        @server.tool
        async def announce(ctx: Context) -> str:
            await ctx.info(f"hello from {name}")
            return name

        return server

    config = MCPConfig(
        mcpServers={
            "alpha": InMemoryServer(mcp=make_logging_server("alpha"), mode="legacy"),
            "beta": InMemoryServer(mcp=make_logging_server("beta"), mode="legacy"),
        }
    )
    records: list[tuple[str, str | None, Any]] = []

    async def log_handler(message: Any, context: GroupCallbackContext) -> None:
        records.append(
            (context.server_name, context.tool_name, message.data.get("msg"))
        )

    group = ClientGroup.from_config(config, log_handler=log_handler)

    async with group:
        await group.call_tool("alpha_announce", {})
        await group.call_tool("beta_announce", {})

    assert ("alpha", None, "hello from alpha") in records
    assert ("beta", None, "hello from beta") in records


async def test_group_progress_handler_receives_call_provenance():
    def make_progress_server(name: str) -> FastMCP:
        server = FastMCP(name)

        @server.tool
        async def work(ctx: Context) -> str:
            await ctx.report_progress(progress=1, total=2)
            return name

        return server

    records: list[tuple[str, str | None, float]] = []

    async def progress_handler(
        progress: float,
        total: float | None,
        message: str | None,
        context: GroupCallbackContext,
    ) -> None:
        records.append((context.server_name, context.tool_name, progress))

    group = ClientGroup(
        {
            "alpha": Client(make_progress_server("alpha")),
            "beta": Client(make_progress_server("beta")),
        },
        progress_handler=progress_handler,
    )

    async with group:
        await group.call_tool("alpha_work", {})
        await group.call_tool("beta_work", {})

    assert ("alpha", "work", 1.0) in records
    assert ("beta", "work", 1.0) in records


async def test_explicit_progress_handler_overrides_group_handler():
    server = FastMCP("only")

    @server.tool
    async def work(ctx: Context) -> str:
        await ctx.report_progress(progress=1, total=1)
        return "done"

    group_calls: list[float] = []
    explicit_calls: list[float] = []

    async def group_handler(
        progress: float,
        total: float | None,
        message: str | None,
        context: GroupCallbackContext,
    ) -> None:
        group_calls.append(progress)

    async def explicit_handler(
        progress: float, total: float | None, message: str | None
    ) -> None:
        explicit_calls.append(progress)

    group = ClientGroup({"only": Client(server)}, progress_handler=group_handler)

    async with group:
        await group.call_tool("only_work", {}, progress_handler=explicit_handler)

    assert explicit_calls == [1.0]
    assert group_calls == []


async def test_from_config_message_handler_receives_provenance():
    from fastmcp.server.middleware import Middleware

    captured: list[Any] = []

    class Capture(Middleware):
        async def on_message(self, context: Any, call_next: Any) -> Any:
            fctx = getattr(context, "fastmcp_context", None)
            if fctx is not None:
                captured.append(fctx.session)
            return await call_next(context)

    server = make_server("alpha")
    server.add_middleware(Capture())
    config = MCPConfig(mcpServers={"alpha": InMemoryServer(mcp=server, mode="legacy")})
    seen: list[str] = []

    async def message_handler(message: Any, context: GroupCallbackContext) -> None:
        seen.append(context.server_name)

    group = ClientGroup.from_config(config, message_handler=message_handler)

    async with group:
        await group.call_tool("alpha_echo", {"value": "hi"})
        # out-of-band server notification on the legacy session
        await captured[-1].send_tool_list_changed()
        await asyncio.sleep(0.1)

    assert "alpha" in seen
