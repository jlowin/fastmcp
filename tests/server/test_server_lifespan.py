"""Tests for server_lifespan and session_lifespan behavior."""

import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from fastmcp import Client, FastMCP
from fastmcp.server.context import Context


class TestServerLifespan:
    """Test server_lifespan functionality."""

    async def test_server_lifespan_basic(self):
        """Test that server_lifespan is entered once and persists across sessions."""
        lifespan_events: list[str] = []

        @asynccontextmanager
        async def server_lifespan(mcp: FastMCP) -> AsyncIterator[dict[str, Any]]:
            _ = lifespan_events.append("enter")
            yield {"initialized": True}
            _ = lifespan_events.append("exit")

        mcp = FastMCP("TestServer", server_lifespan=server_lifespan)

        @mcp.tool
        def get_value() -> str:
            return "test"

        # Server lifespan should be entered when run_async starts
        assert lifespan_events == []

        # Connect first client session
        async with Client(mcp) as client1:
            result1 = await client1.call_tool("get_value", {})
            assert result1.data == "test"
            # Server lifespan should have been entered once
            assert lifespan_events == ["enter"]

            # Connect second client session while first is still active
            async with Client(mcp) as client2:
                result2 = await client2.call_tool("get_value", {})
                assert result2.data == "test"
                # Server lifespan should still only have been entered once
                assert lifespan_events == ["enter"]

        # Because we're using a fastmcptransport, the server lifespan should be exited
        # when the client session closes
        assert lifespan_events == ["enter", "exit"]

    async def test_server_lifespan_context_available(self):
        """Test that server_lifespan context is available to tools."""

        @asynccontextmanager
        async def server_lifespan(mcp: FastMCP) -> AsyncIterator[dict]:
            yield {"db_connection": "mock_db"}

        mcp = FastMCP("TestServer", server_lifespan=server_lifespan)

        @mcp.tool
        def get_db_info(ctx: Context) -> str:
            # Access the server lifespan context
            lifespan_context = ctx.request_context.lifespan_context
            return lifespan_context.get("db_connection", "no_db")

        async with Client(mcp) as client:
            result = await client.call_tool("get_db_info", {})
            assert result.data == "mock_db"

    async def test_has_lifespan_flag_server_lifespan(self):
        """Test that _has_lifespan is True when server_lifespan is provided."""

        @asynccontextmanager
        async def server_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            yield

        mcp = FastMCP("TestServer", server_lifespan=server_lifespan)
        assert mcp._has_lifespan is True

    async def test_has_lifespan_flag_no_lifespan(self):
        """Test that _has_lifespan is False when no lifespan is provided."""
        mcp = FastMCP("TestServer")
        assert mcp._has_lifespan is False


class TestSessionLifespan:
    """Test session_lifespan functionality (deprecated but still supported)."""

    async def test_session_lifespan_deprecation_warning(self):
        """Test that using session_lifespan triggers a deprecation warning."""

        @asynccontextmanager
        async def session_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            yield

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = FastMCP(name="TestServer", session_lifespan=session_lifespan)

            # Should have emitted a deprecation warning
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "session_lifespan parameter is deprecated" in str(w[0].message)
            assert "use the lifespan parameter instead" in str(w[0].message)

    async def test_session_lifespan_still_works(self):
        """Test that session_lifespan still functions despite deprecation."""
        session_events = []

        @asynccontextmanager
        async def session_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            session_events.append("enter")
            yield
            session_events.append("exit")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mcp = FastMCP("TestServer", session_lifespan=session_lifespan)

        @mcp.tool
        def test_tool() -> str:
            return "ok"

        async with Client(mcp) as client:
            await client.call_tool("test_tool", {})
            # Session lifespan should have been entered
            assert "enter" in session_events

    async def test_lifespan_aliases_to_session_lifespan(self):
        """Test that lifespan parameter is used as session_lifespan when session_lifespan is not provided."""
        lifespan_events = []

        @asynccontextmanager
        async def my_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            lifespan_events.append("enter")
            yield
            lifespan_events.append("exit")

        # Use lifespan parameter (not session_lifespan)
        mcp = FastMCP("TestServer", lifespan=my_lifespan)

        @mcp.tool
        def test_tool() -> str:
            return "ok"

        async with Client(mcp) as client:
            await client.call_tool("test_tool", {})
            assert "enter" in lifespan_events

    async def test_has_lifespan_flag_session_lifespan(self):
        """Test that _has_lifespan is True when session_lifespan is provided."""

        @asynccontextmanager
        async def session_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            yield

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            mcp = FastMCP("TestServer", session_lifespan=session_lifespan)

        assert mcp._has_lifespan is True


class TestLifespanConflicts:
    """Test conflicts between different lifespan parameters."""

    async def test_conflict_session_and_server_lifespan(self):
        """Test that providing both session_lifespan and server_lifespan raises an error."""

        @asynccontextmanager
        async def session_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            yield

        @asynccontextmanager
        async def server_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            yield

        with pytest.raises(
            ValueError, match="Cannot specify both session_lifespan and server_lifespan"
        ):
            FastMCP(
                "TestServer",
                session_lifespan=session_lifespan,
                server_lifespan=server_lifespan,
            )

    async def test_lifespan_with_server_lifespan_ok(self):
        """Test that providing both lifespan and server_lifespan works (lifespan is ignored)."""
        lifespan_events = []
        server_lifespan_events = []

        @asynccontextmanager
        async def my_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            lifespan_events.append("enter")
            yield
            lifespan_events.append("exit")

        @asynccontextmanager
        async def my_server_lifespan(mcp: FastMCP) -> AsyncIterator[None]:
            server_lifespan_events.append("enter")
            yield
            server_lifespan_events.append("exit")

        # This should work - lifespan is used as fallback for session_lifespan
        # when session_lifespan is not provided
        mcp = FastMCP(
            "TestServer", lifespan=my_lifespan, server_lifespan=my_server_lifespan
        )

        @mcp.tool
        def test_tool() -> str:
            return "ok"

        async with Client(mcp) as client:
            await client.call_tool("test_tool", {})
            # Server lifespan should be used
            assert len(server_lifespan_events) > 0
            # Session lifespan (from lifespan param) should also be entered
            assert len(lifespan_events) > 0
