"""Tests for providers."""

from typing import Any

import pytest
from mcp.types import Tool as MCPTool

from fastmcp import FastMCP, Provider
from fastmcp.client import Client
from fastmcp.client.client import CallToolResult
from fastmcp.server.context import Context
from fastmcp.tools.tool import Tool, ToolResult


class SimpleTool(Tool):
    """A simple tool for testing that performs a configured operation."""

    operation: str
    value: int = 0

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        a = arguments.get("a", 0)
        b = arguments.get("b", 0)

        if self.operation == "add":
            result = a + b + self.value
        elif self.operation == "multiply":
            result = a * b + self.value
        else:
            result = a + b

        return ToolResult(
            structured_content={"result": result, "operation": self.operation}
        )


class SimpleToolProvider(Provider):
    """A simple provider that returns a configurable list of tools."""

    def __init__(self, tools: list[Tool] | None = None):
        self._tools = tools or []
        self.list_tools_call_count = 0
        self.get_tool_call_count = 0

    async def list_tools(self, context: Context) -> list[Tool]:
        self.list_tools_call_count += 1
        return self._tools

    async def get_tool(self, context: Context, name: str) -> Tool | None:
        self.get_tool_call_count += 1
        return next((t for t in self._tools if t.name == name), None)


class ListOnlyProvider(Provider):
    """A provider that only implements list_tools (uses default get_tool)."""

    def __init__(self, tools: list[Tool]):
        self._tools = tools
        self.list_tools_call_count = 0

    async def list_tools(self, context: Context) -> list[Tool]:
        self.list_tools_call_count += 1
        return self._tools


class TestProvider:
    """Tests for Provider."""

    @pytest.fixture
    def base_server(self):
        """Create a base FastMCP server with static tools."""
        mcp = FastMCP("BaseServer")

        @mcp.tool
        def static_add(a: int, b: int) -> int:
            """Add two numbers (static tool)."""
            return a + b

        @mcp.tool
        def static_subtract(a: int, b: int) -> int:
            """Subtract two numbers (static tool)."""
            return a - b

        return mcp

    @pytest.fixture
    def dynamic_tools(self) -> list[Tool]:
        """Create dynamic tools for testing."""
        return [
            SimpleTool(
                name="dynamic_multiply",
                description="Multiply two numbers",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                },
                operation="multiply",
            ),
            SimpleTool(
                name="dynamic_add",
                description="Add two numbers with offset",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                },
                operation="add",
                value=100,
            ),
        ]

    async def test_list_tools_includes_dynamic_tools(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that list_tools returns both static and dynamic tools."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            tools: list[MCPTool] = await client.list_tools()

        # Should have all tools: 2 static + 2 dynamic
        assert len(tools) == 4
        tool_names = [tool.name for tool in tools]
        assert "static_add" in tool_names
        assert "static_subtract" in tool_names
        assert "dynamic_multiply" in tool_names
        assert "dynamic_add" in tool_names

    async def test_list_tools_calls_provider_each_time(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that provider.list_tools() is called on every list_tools request."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            # Call list_tools multiple times
            await client.list_tools()
            await client.list_tools()
            await client.list_tools()

        # Provider should have been called 3 times
        assert provider.list_tools_call_count == 3

    async def test_call_dynamic_tool(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that dynamic tools can be called successfully."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            result: CallToolResult = await client.call_tool(
                name="dynamic_multiply", arguments={"a": 7, "b": 6}
            )

        assert result.structured_content is not None
        assert result.structured_content["result"] == 42  # type: ignore[attr-defined]
        assert result.structured_content["operation"] == "multiply"  # type: ignore[attr-defined]

    async def test_call_dynamic_tool_with_config(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that dynamic tool config (like value offset) is used."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            result: CallToolResult = await client.call_tool(
                name="dynamic_add", arguments={"a": 5, "b": 3}
            )

        assert result.structured_content is not None
        # 5 + 3 + 100 (value offset) = 108
        assert result.structured_content["result"] == 108  # type: ignore[attr-defined]

    async def test_call_static_tool_still_works(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that static tools still work after adding dynamic tools."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            result: CallToolResult = await client.call_tool(
                name="static_add", arguments={"a": 10, "b": 5}
            )

        assert result.structured_content is not None
        assert result.structured_content["result"] == 15  # type: ignore[attr-defined]

    async def test_call_tool_uses_get_tool_for_efficient_lookup(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that call_tool uses get_tool() for efficient single-tool lookup."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            await client.call_tool(name="dynamic_multiply", arguments={"a": 2, "b": 3})

        # get_tool should have been called (not list_tools)
        assert provider.get_tool_call_count == 1

    async def test_default_get_tool_falls_back_to_list(self, base_server: FastMCP):
        """Test that BaseToolProvider's default get_tool calls list_tools."""
        tools = [
            SimpleTool(
                name="test_tool",
                description="A test tool",
                parameters={"type": "object", "properties": {}},
                operation="add",
            ),
        ]
        provider = ListOnlyProvider(tools=tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            result = await client.call_tool(
                name="test_tool", arguments={"a": 1, "b": 2}
            )

        assert result.structured_content is not None
        # Default get_tool should have called list_tools
        assert provider.list_tools_call_count >= 1

    async def test_dynamic_tools_come_first(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that dynamic tools appear before static tools in list."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            tools: list[MCPTool] = await client.list_tools()

        tool_names = [tool.name for tool in tools]
        # Dynamic tools should come first
        assert tool_names[:2] == ["dynamic_multiply", "dynamic_add"]

    async def test_empty_provider(self, base_server: FastMCP):
        """Test that empty provider doesn't affect behavior."""
        provider = SimpleToolProvider(tools=[])
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            tools: list[MCPTool] = await client.list_tools()

        # Should only have static tools
        assert len(tools) == 2

    async def test_tool_not_found_falls_through_to_static(
        self, base_server: FastMCP, dynamic_tools: list[Tool]
    ):
        """Test that unknown tool name falls through to static tools."""
        provider = SimpleToolProvider(tools=dynamic_tools)
        base_server.add_provider(provider)

        async with Client(base_server) as client:
            # This tool is static, not in the dynamic provider
            result: CallToolResult = await client.call_tool(
                name="static_subtract", arguments={"a": 10, "b": 3}
            )

        assert result.structured_content is not None
        assert result.structured_content["result"] == 7  # type: ignore[attr-defined]


class TestProviderClass:
    """Tests for the Provider class."""

    async def test_subclass_is_instance(self):
        """Test that subclasses are instances of Provider."""
        provider = SimpleToolProvider(tools=[])
        assert isinstance(provider, Provider)

    async def test_default_get_tool_works(self):
        """Test that the default get_tool implementation works."""
        tool = SimpleTool(
            name="test",
            description="Test",
            parameters={"type": "object", "properties": {}},
            operation="add",
        )
        provider = ListOnlyProvider(tools=[tool])

        # Create a context for direct testing
        mcp = FastMCP("TestServer")
        ctx = Context(mcp)

        # Default get_tool should find by name
        found = await provider.get_tool(ctx, "test")
        assert found is not None
        assert found.name == "test"

        # Should return None for unknown names
        not_found = await provider.get_tool(ctx, "unknown")
        assert not_found is None


class TestDynamicToolUpdates:
    """Tests demonstrating dynamic tool updates without restart."""

    async def test_tools_update_without_restart(self):
        """Test that tools can be updated dynamically."""
        mcp = FastMCP("DynamicServer")

        # Start with one tool
        initial_tools = [
            SimpleTool(
                name="tool_v1",
                description="Version 1",
                parameters={"type": "object", "properties": {}},
                operation="add",
            ),
        ]
        provider = SimpleToolProvider(tools=initial_tools)
        mcp.add_provider(provider)

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 1
            assert tools[0].name == "tool_v1"

            # Update the provider's tools (simulating DB update)
            provider._tools = [
                SimpleTool(
                    name="tool_v2",
                    description="Version 2",
                    parameters={"type": "object", "properties": {}},
                    operation="multiply",
                ),
                SimpleTool(
                    name="tool_v3",
                    description="Version 3",
                    parameters={"type": "object", "properties": {}},
                    operation="add",
                ),
            ]

            # List tools again - should see new tools
            tools = await client.list_tools()
            assert len(tools) == 2
            tool_names = [t.name for t in tools]
            assert "tool_v1" not in tool_names
            assert "tool_v2" in tool_names
            assert "tool_v3" in tool_names
