"""Tests for OpenTelemetry middleware."""

import pytest

from fastmcp import Client, FastMCP


class TestOpenTelemetryMiddlewareWithoutOTel:
    """Test OpenTelemetry middleware behavior when opentelemetry is not installed."""

    async def test_middleware_no_op_without_opentelemetry(self):
        """Test that middleware works as a no-op when OpenTelemetry is not installed."""
        # Import after potentially uninstalling opentelemetry
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.tool()
        def test_tool(value: str) -> str:
            return f"result: {value}"

        # Should work without errors even if OpenTelemetry is not installed
        async with Client(mcp) as client:
            result = await client.call_tool("test_tool", {"value": "test"})
            assert result.content[0].text == "result: test"  # type: ignore[attr-defined]


class TestOpenTelemetryMiddlewareConfiguration:
    """Test OpenTelemetry middleware configuration options."""

    def test_middleware_can_be_disabled(self):
        """Test that middleware can be explicitly disabled."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        middleware = OpenTelemetryMiddleware(enabled=False)
        mcp.add_middleware(middleware)

        assert middleware.enabled is False
        assert middleware.tracer is None

    def test_middleware_respects_include_arguments(self):
        """Test that include_arguments parameter is respected."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        middleware = OpenTelemetryMiddleware(include_arguments=False)
        assert middleware.include_arguments is False

        middleware = OpenTelemetryMiddleware(include_arguments=True)
        assert middleware.include_arguments is True

    def test_middleware_respects_max_argument_length(self):
        """Test that max_argument_length parameter is respected."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        middleware = OpenTelemetryMiddleware(max_argument_length=100)
        assert middleware.max_argument_length == 100

        # Test truncation
        long_value = "x" * 200
        truncated = middleware._truncate_value(long_value)
        assert len(truncated) == 103  # 100 + "..."
        assert truncated.endswith("...")


class TestOpenTelemetryMiddlewareOperations:
    """Test that middleware handles different MCP operations."""

    async def test_tool_call_without_errors(self):
        """Test that middleware handles tool calls without errors."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.tool()
        def test_tool(value: str) -> str:
            return f"result: {value}"

        async with Client(mcp) as client:
            result = await client.call_tool("test_tool", {"value": "test"})
            assert result.content[0].text == "result: test"  # type: ignore[attr-defined]

    async def test_resource_read_without_errors(self):
        """Test that middleware handles resource reads without errors."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.resource("test://resource")
        def test_resource() -> str:
            return "resource content"

        async with Client(mcp) as client:
            result = await client.read_resource("test://resource")
            assert result[0].text == "resource content"  # type: ignore[attr-defined]

    async def test_prompt_get_without_errors(self):
        """Test that middleware handles prompt retrieval without errors."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.prompt()
        def test_prompt(name: str) -> str:
            return f"Hello, {name}!"

        async with Client(mcp) as client:
            result = await client.get_prompt("test_prompt", {"name": "World"})
            assert any("Hello, World!" in str(msg) for msg in result.messages)

    async def test_list_tools_without_errors(self):
        """Test that middleware handles list tools without errors."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.tool()
        def test_tool() -> str:
            return "test"

        async with Client(mcp) as client:
            result = await client.list_tools()
            assert len(result) == 1
            assert result[0].name == "test_tool"

    async def test_list_resources_without_errors(self):
        """Test that middleware handles list resources without errors."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.resource("test://resource")
        def test_resource() -> str:
            return "test"

        async with Client(mcp) as client:
            result = await client.list_resources()
            assert len(result) == 1
            assert str(result[0].uri) == "test://resource"

    async def test_list_prompts_without_errors(self):
        """Test that middleware handles list prompts without errors."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.prompt()
        def test_prompt() -> str:
            return "test"

        async with Client(mcp) as client:
            result = await client.list_prompts()
            assert len(result) == 1
            assert result[0].name == "test_prompt"


class TestOpenTelemetryMiddlewareErrorHandling:
    """Test that middleware properly handles errors."""

    async def test_tool_error_propagates(self):
        """Test that errors in tools are properly propagated."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware())

        @mcp.tool()
        def failing_tool() -> str:
            raise ValueError("Test error")

        async with Client(mcp) as client:
            with pytest.raises(Exception):
                await client.call_tool("failing_tool", {})
