"""Tests for bulk tool caller middleware."""

import pytest
from inline_snapshot import snapshot

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.server.middleware import BulkToolCallerMiddleware


class ToolException(Exception):
    """Custom exception for tool errors."""


@pytest.fixture
def server_with_tools():
    """Create a FastMCP server with bulk tool caller middleware and test tools."""
    mcp = FastMCP("BulkToolServer", middleware=[BulkToolCallerMiddleware()])

    @mcp.tool
    async def echo_tool(arg1: str) -> str:
        """A simple tool that echoes arguments."""
        return arg1

    @mcp.tool
    async def error_tool(arg1: str) -> str:
        """A tool that raises an error for testing purposes."""
        raise ToolException(f"Error in tool with arg1: {arg1}")

    @mcp.tool
    async def no_return_tool(arg1: str) -> None:
        """A simple tool that returns nothing."""

    @mcp.tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    return mcp


class TestBulkToolCallerMiddleware:
    """Tests for BulkToolCallerMiddleware."""

    async def test_middleware_adds_bulk_tools(self, server_with_tools: FastMCP):
        """Test that the middleware adds the bulk tool caller tools."""
        async with Client(server_with_tools) as client:
            tools = await client.list_tools()

        tool_names = [tool.name for tool in tools]
        # Should have: echo_tool, error_tool, no_return_tool, add, call_tools_bulk, call_tool_bulk
        assert len(tools) == 6
        assert "call_tools_bulk" in tool_names
        assert "call_tool_bulk" in tool_names
        assert "echo_tool" in tool_names
        assert "error_tool" in tool_names
        assert "no_return_tool" in tool_names
        assert "add" in tool_names

    async def test_call_tool_bulk_single_success(self, server_with_tools: FastMCP):
        """Test single successful call via call_tool_bulk."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tool_bulk",
                {"tool": "echo_tool", "tool_arguments": [{"arg1": "value1"}]},
            )

        assert result.structured_content is not None
        assert result.structured_content["result"] == snapshot(
            [
                {
                    "_meta": None,
                    "content": [
                        {
                            "type": "text",
                            "text": "value1",
                            "annotations": None,
                            "_meta": None,
                        }
                    ],
                    "structuredContent": None,
                    "isError": False,
                    "tool": "echo_tool",
                    "arguments": {"arg1": "value1"},
                }
            ]
        )

    async def test_call_tool_bulk_multiple_success(self, server_with_tools: FastMCP):
        """Test multiple successful calls via call_tool_bulk."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tool_bulk",
                {
                    "tool": "echo_tool",
                    "tool_arguments": [{"arg1": "value1"}, {"arg1": "value2"}],
                },
            )

        assert result.structured_content is not None
        assert result.structured_content["result"] == snapshot(
            [
                {
                    "_meta": None,
                    "content": [
                        {
                            "type": "text",
                            "text": "value1",
                            "annotations": None,
                            "_meta": None,
                        }
                    ],
                    "structuredContent": None,
                    "isError": False,
                    "tool": "echo_tool",
                    "arguments": {"arg1": "value1"},
                },
                {
                    "_meta": None,
                    "content": [
                        {
                            "type": "text",
                            "text": "value2",
                            "annotations": None,
                            "_meta": None,
                        }
                    ],
                    "structuredContent": None,
                    "isError": False,
                    "tool": "echo_tool",
                    "arguments": {"arg1": "value2"},
                },
            ]
        )

    async def test_call_tool_bulk_error_stops(self, server_with_tools: FastMCP):
        """Test call_tool_bulk stops on first error."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tool_bulk",
                {
                    "tool": "error_tool",
                    "tool_arguments": [{"arg1": "error_value"}, {"arg1": "value2"}],
                    "continue_on_error": False,
                },
            )

        assert result.structured_content is not None
        results = result.structured_content["result"]  # type: ignore[attr-defined]
        assert len(results) == 1
        assert results[0]["isError"] is True
        assert (
            "Error in tool with arg1: error_value" in results[0]["content"][0]["text"]
        )

    async def test_call_tool_bulk_error_continues(self, server_with_tools: FastMCP):
        """Test call_tool_bulk continues on error."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tool_bulk",
                {
                    "tool": "error_tool",
                    "tool_arguments": [{"arg1": "error_value"}, {"arg1": "value2"}],
                    "continue_on_error": True,
                },
            )

        assert result.structured_content is not None
        results = result.structured_content["result"]  # type: ignore[attr-defined]
        # Both should be errors since the tool always raises
        assert len(results) == 2
        assert results[0]["isError"] is True
        assert results[1]["isError"] is True

    async def test_call_tools_bulk_single_success(self, server_with_tools: FastMCP):
        """Test single successful call via call_tools_bulk."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tools_bulk",
                {
                    "tool_calls": [
                        {"tool": "echo_tool", "arguments": {"arg1": "value1"}}
                    ]
                },
            )

        assert result.structured_content is not None
        assert result.structured_content["result"] == snapshot(
            [
                {
                    "_meta": None,
                    "content": [
                        {
                            "type": "text",
                            "text": "value1",
                            "annotations": None,
                            "_meta": None,
                        }
                    ],
                    "structuredContent": None,
                    "isError": False,
                    "tool": "echo_tool",
                    "arguments": {"arg1": "value1"},
                }
            ]
        )

    async def test_call_tools_bulk_multiple_different_tools(
        self, server_with_tools: FastMCP
    ):
        """Test multiple successful calls via call_tools_bulk with different tools."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tools_bulk",
                {
                    "tool_calls": [
                        {"tool": "echo_tool", "arguments": {"arg1": "echo_value"}},
                        {"tool": "add", "arguments": {"a": 5, "b": 3}},
                    ]
                },
            )

        assert result.structured_content is not None
        results = result.structured_content["result"]  # type: ignore[attr-defined]
        assert len(results) == 2
        assert results[0]["tool"] == "echo_tool"
        assert results[0]["content"][0]["text"] == "echo_value"
        assert results[1]["tool"] == "add"
        assert results[1]["content"][0]["text"] == "8"

    async def test_call_tools_bulk_error_stops(self, server_with_tools: FastMCP):
        """Test call_tools_bulk stops on first error."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tools_bulk",
                {
                    "tool_calls": [
                        {"tool": "error_tool", "arguments": {"arg1": "error_value"}},
                        {"tool": "echo_tool", "arguments": {"arg1": "skipped_value"}},
                    ],
                    "continue_on_error": False,
                },
            )

        assert result.structured_content is not None
        results = result.structured_content["result"]  # type: ignore[attr-defined]
        # Should only have one result (stopped on error)
        assert len(results) == 1
        assert results[0]["isError"] is True
        assert (
            "Error in tool with arg1: error_value" in results[0]["content"][0]["text"]
        )

    async def test_call_tools_bulk_error_continues(self, server_with_tools: FastMCP):
        """Test call_tools_bulk continues on error."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tools_bulk",
                {
                    "tool_calls": [
                        {"tool": "error_tool", "arguments": {"arg1": "error_value"}},
                        {"tool": "echo_tool", "arguments": {"arg1": "success_value"}},
                    ],
                    "continue_on_error": True,
                },
            )

        assert result.structured_content is not None
        results = result.structured_content["result"]  # type: ignore[attr-defined]
        # Should have both results
        assert len(results) == 2
        assert results[0]["isError"] is True
        assert results[0]["tool"] == "error_tool"
        # isError can be None or False for successful calls
        assert results[1]["isError"] in (None, False)
        assert results[1]["tool"] == "echo_tool"
        assert results[1]["content"][0]["text"] == "success_value"

    async def test_call_tools_bulk_with_no_return_tool(
        self, server_with_tools: FastMCP
    ):
        """Test calling tools that return None."""
        async with Client(server_with_tools) as client:
            result = await client.call_tool(
                "call_tools_bulk",
                {
                    "tool_calls": [
                        {
                            "tool": "no_return_tool",
                            "arguments": {"arg1": "no_return_value"},
                        }
                    ]
                },
            )

        assert result.structured_content is not None
        results = result.structured_content["result"]  # type: ignore[attr-defined]
        assert len(results) == 1
        assert results[0]["tool"] == "no_return_tool"
        assert results[0]["content"] == []

    async def test_bulk_tools_bypass_filtering(self):
        """Test that bulk caller tools bypass tag filtering."""
        mcp = FastMCP(
            "FilteredServer",
            middleware=[BulkToolCallerMiddleware()],
            exclude_tags={"math"},
        )

        @mcp.tool(tags={"math"})
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        async with Client(mcp) as client:
            tools = await client.list_tools()

        tool_names = [tool.name for tool in tools]
        # The multiply tool should be filtered out, but bulk tools should still be available
        assert "call_tools_bulk" in tool_names
        assert "call_tool_bulk" in tool_names
        assert "multiply" not in tool_names


class TestBulkToolCallerDeprecation:
    """Tests for BulkToolCaller deprecation warnings."""

    async def test_old_bulk_tool_caller_shows_deprecation(self):
        """Test that using BulkToolCaller shows deprecation warning."""
        from fastmcp.contrib.bulk_tool_caller.bulk_tool_caller import BulkToolCaller

        mcp = FastMCP("OldStyleServer")

        @mcp.tool
        def echo(text: str) -> str:
            return text

        with pytest.warns(DeprecationWarning, match="BulkToolCaller is deprecated"):
            bulk_tool_caller = BulkToolCaller()
            bulk_tool_caller.register_tools(mcp)

    async def test_old_bulk_tool_caller_still_works(self):
        """Test that old BulkToolCaller still functions correctly."""
        from fastmcp.contrib.bulk_tool_caller.bulk_tool_caller import BulkToolCaller

        mcp = FastMCP("OldStyleServer")

        @mcp.tool
        def echo(text: str) -> str:
            return text

        with pytest.warns(DeprecationWarning):
            bulk_tool_caller = BulkToolCaller()
            bulk_tool_caller.register_tools(mcp)

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]
            assert "call_tools_bulk" in tool_names
            assert "call_tool_bulk" in tool_names

            # Test that it actually works
            result = await client.call_tool(
                "call_tool_bulk",
                {"tool": "echo", "tool_arguments": [{"text": "hello"}]},
            )

        # The old BulkToolCaller returns text content (not structured), so just verify it doesn't error
        assert result.content is not None
        assert len(result.content) > 0
