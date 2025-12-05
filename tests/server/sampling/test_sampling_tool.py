"""Tests for SamplingTool."""

import pytest

from fastmcp.server.sampling import SamplingTool
from fastmcp.tools.tool import Tool


class TestSamplingToolFromFunction:
    """Tests for SamplingTool.from_function()."""

    def test_from_simple_function(self):
        def search(query: str) -> str:
            """Search the web."""
            return f"Results for: {query}"

        tool = SamplingTool.from_function(search)

        assert tool.name == "search"
        assert tool.description == "Search the web."
        assert "query" in tool.parameters.get("properties", {})
        assert tool.fn is search

    def test_from_function_with_overrides(self):
        def search(query: str) -> str:
            return f"Results for: {query}"

        tool = SamplingTool.from_function(
            search,
            name="web_search",
            description="Search the internet",
        )

        assert tool.name == "web_search"
        assert tool.description == "Search the internet"

    def test_from_lambda_requires_name(self):
        with pytest.raises(ValueError, match="must provide a name for lambda"):
            SamplingTool.from_function(lambda x: x)

    def test_from_lambda_with_name(self):
        tool = SamplingTool.from_function(lambda x: x * 2, name="double")

        assert tool.name == "double"

    def test_from_async_function(self):
        async def async_search(query: str) -> str:
            """Async search."""
            return f"Async results for: {query}"

        tool = SamplingTool.from_function(async_search)

        assert tool.name == "async_search"
        assert tool.description == "Async search."

    def test_multiple_parameters(self):
        def search(query: str, limit: int = 10, include_images: bool = False) -> str:
            """Search with options."""
            return f"Results for: {query}"

        tool = SamplingTool.from_function(search)
        props = tool.parameters.get("properties", {})

        assert "query" in props
        assert "limit" in props
        assert "include_images" in props


class TestSamplingToolFromMCPTool:
    """Tests for SamplingTool.from_mcp_tool()."""

    def test_from_function_tool(self):
        def original(x: int) -> int:
            """Double a number."""
            return x * 2

        mcp_tool = Tool.from_function(original)
        sampling = SamplingTool.from_mcp_tool(mcp_tool)

        assert sampling.name == "original"
        assert sampling.description == "Double a number."
        assert sampling.fn is mcp_tool.fn

    def test_from_tool_without_fn_raises(self):
        # Create a base Tool without fn (not a FunctionTool)
        tool = Tool(
            name="test",
            description="Test tool",
            parameters={"type": "object"},
            tags=set(),
        )

        with pytest.raises(ValueError, match="does not have an fn attribute"):
            SamplingTool.from_mcp_tool(tool)


class TestSamplingToolRun:
    """Tests for SamplingTool.run()."""

    async def test_run_sync_function(self):
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        tool = SamplingTool.from_function(add)
        result = await tool.run({"a": 2, "b": 3})
        assert result == 5

    async def test_run_async_function(self):
        async def async_add(a: int, b: int) -> int:
            """Add two numbers asynchronously."""
            return a + b

        tool = SamplingTool.from_function(async_add)
        result = await tool.run({"a": 2, "b": 3})
        assert result == 5

    async def test_run_with_no_arguments(self):
        def get_value() -> str:
            """Return a fixed value."""
            return "hello"

        tool = SamplingTool.from_function(get_value)
        result = await tool.run()
        assert result == "hello"

    async def test_run_with_none_arguments(self):
        def get_value() -> str:
            """Return a fixed value."""
            return "hello"

        tool = SamplingTool.from_function(get_value)
        result = await tool.run(None)
        assert result == "hello"


class TestSamplingToolSDKConversion:
    """Tests for SamplingTool._to_sdk_tool() internal method."""

    def test_to_sdk_tool(self):
        def search(query: str) -> str:
            """Search the web."""
            return f"Results for: {query}"

        tool = SamplingTool.from_function(search)
        sdk_tool = tool._to_sdk_tool()

        assert sdk_tool.name == "search"
        assert sdk_tool.description == "Search the web."
        assert "query" in sdk_tool.inputSchema.get("properties", {})
