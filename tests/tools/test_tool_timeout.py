"""Tests for tool timeout and Docket dependency detection."""

import time

import anyio
import pytest
from mcp.types import TextContent

from fastmcp import FastMCP


def _docket_available() -> bool:
    """Check if Docket is available."""
    try:
        import docket  # noqa: F401

        return True
    except ImportError:
        return False


class TestToolExecution:
    """Test basic tool execution (timeout parameter removed in v3.0.0b2)."""

    async def test_async_tool_completes_normally(self):
        """Async tool completes normally."""
        mcp = FastMCP()

        @mcp.tool
        async def quick_async_tool() -> str:
            await anyio.sleep(0.01)
            return "completed"

        result = await mcp.call_tool("quick_async_tool")
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "completed"

    async def test_sync_tool_completes_normally(self):
        """Sync tool completes normally."""
        mcp = FastMCP()

        @mcp.tool
        def quick_sync_tool() -> str:
            time.sleep(0.01)
            return "completed"

        result = await mcp.call_tool("quick_sync_tool")
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == "completed"

    async def test_multiple_tools_complete_normally(self):
        """Multiple tools can run and complete."""
        mcp = FastMCP()

        @mcp.tool
        async def tool_one() -> str:
            await anyio.sleep(0.01)
            return "one"

        @mcp.tool
        async def tool_two() -> str:
            await anyio.sleep(0.01)
            return "two"

        @mcp.tool
        def tool_three() -> str:
            time.sleep(0.01)
            return "three"

        result1 = await mcp.call_tool("tool_one")
        result2 = await mcp.call_tool("tool_two")
        result3 = await mcp.call_tool("tool_three")

        assert isinstance(result1.content[0], TextContent)
        assert isinstance(result2.content[0], TextContent)
        assert isinstance(result3.content[0], TextContent)
        assert result1.content[0].text == "one"
        assert result2.content[0].text == "two"
        assert result3.content[0].text == "three"


class TestDocketCallableProperty:
    """Test the docket_callable property on components."""

    async def test_function_tool_docket_callable_returns_fn(self):
        """FunctionTool.docket_callable returns the underlying function."""
        from fastmcp.tools import Tool

        async def my_tool() -> str:
            return "result"

        tool = Tool.from_function(my_tool)
        # FunctionTool should return self.fn
        assert tool.docket_callable is not None
        # It should be callable
        assert callable(tool.docket_callable)

    async def test_function_resource_docket_callable_returns_fn(self):
        """FunctionResource.docket_callable returns the underlying function."""
        from fastmcp.resources import Resource

        def my_resource() -> str:
            return "data"

        resource = Resource.from_function(my_resource, uri="data://test")
        assert resource.docket_callable is not None
        assert callable(resource.docket_callable)

    async def test_function_prompt_docket_callable_returns_fn(self):
        """FunctionPrompt.docket_callable returns the underlying function."""
        from fastmcp.prompts import Prompt

        def my_prompt(topic: str) -> str:
            return f"Write about {topic}"

        prompt = Prompt.from_function(my_prompt)
        assert prompt.docket_callable is not None
        assert callable(prompt.docket_callable)


class TestRequiresDocketExecution:
    """Test the requires_docket_execution() function."""

    def test_tool_without_docket_deps_returns_false(self):
        """Tool without Docket dependencies returns False."""
        from fastmcp.server.dependencies import requires_docket_execution
        from fastmcp.tools import Tool

        async def simple_tool(x: int) -> int:
            return x * 2

        tool = Tool.from_function(simple_tool)
        assert requires_docket_execution(tool) is False

    def test_tool_with_regular_deps_returns_false(self):
        """Tool with regular (non-Docket) dependencies returns False."""
        from fastmcp.server.context import Context
        from fastmcp.server.dependencies import requires_docket_execution
        from fastmcp.tools import Tool

        async def tool_with_context(x: int, ctx: Context) -> int:
            return x * 2

        tool = Tool.from_function(tool_with_context)
        assert requires_docket_execution(tool) is False

    def test_component_without_docket_callable_returns_false(self):
        """Component without docket_callable returns False."""
        from fastmcp.server.dependencies import requires_docket_execution

        class FakeComponent:
            pass

        assert requires_docket_execution(FakeComponent()) is False

    @pytest.mark.skipif(
        not _docket_available(),
        reason="Docket not installed",
    )
    def test_tool_with_timeout_dep_returns_true(self):
        """Tool with Docket Timeout dependency returns True."""
        from datetime import timedelta

        from docket import Timeout

        from fastmcp.server.dependencies import requires_docket_execution
        from fastmcp.tools import Tool

        async def tool_with_timeout(
            x: int,
            timeout: Timeout = Timeout(timedelta(seconds=30)),
        ) -> int:
            return x * 2

        tool = Tool.from_function(tool_with_timeout)
        assert requires_docket_execution(tool) is True

    @pytest.mark.skipif(
        not _docket_available(),
        reason="Docket not installed",
    )
    def test_tool_with_retry_dep_returns_true(self):
        """Tool with Docket Retry dependency returns True."""
        from docket import ExponentialRetry

        from fastmcp.server.dependencies import requires_docket_execution
        from fastmcp.tools import Tool

        async def tool_with_retry(
            x: int,
            retry: ExponentialRetry = ExponentialRetry(attempts=3),
        ) -> int:
            return x * 2

        tool = Tool.from_function(tool_with_retry)
        assert requires_docket_execution(tool) is True
