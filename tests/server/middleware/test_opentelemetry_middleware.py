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


class TestOpenTelemetryMiddlewareContextPropagation:
    """Test trace context propagation through MCP _meta fields."""

    def test_propagate_context_can_be_disabled(self):
        """Test that context propagation can be disabled."""
        from fastmcp.server.middleware.opentelemetry import OpenTelemetryMiddleware

        middleware = OpenTelemetryMiddleware(propagate_context=False)
        assert middleware.propagate_context is False
        assert middleware.propagator is None

    def test_propagate_context_enabled_by_default(self):
        """Test that context propagation is enabled by default when OTel is available."""
        from fastmcp.server.middleware.opentelemetry import (
            OPENTELEMETRY_AVAILABLE,
            OpenTelemetryMiddleware,
        )

        middleware = OpenTelemetryMiddleware()
        assert middleware.propagate_context is True
        if OPENTELEMETRY_AVAILABLE:
            assert middleware.propagator is not None
        else:
            assert middleware.propagator is None

    async def test_trace_context_injection_in_tool_result(self):
        """Test that trace context is injected into tool result metadata."""
        from fastmcp.server.middleware.opentelemetry import (
            OPENTELEMETRY_AVAILABLE,
            OpenTelemetryMiddleware,
        )

        if not OPENTELEMETRY_AVAILABLE:
            pytest.skip("OpenTelemetry not available")

        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        # Set up a tracer provider
        trace.set_tracer_provider(TracerProvider())

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware(propagate_context=True))

        @mcp.tool()
        def test_tool(value: str) -> str:
            return f"result: {value}"

        async with Client(mcp) as client:
            result = await client.call_tool("test_tool", {"value": "test"})
            # Check that result has metadata with trace context
            assert result.meta is not None
            assert "traceparent" in result.meta

    async def test_trace_context_extraction_from_request(self):
        """Test that trace context is extracted from request metadata."""
        from fastmcp.server.middleware.opentelemetry import (
            OPENTELEMETRY_AVAILABLE,
            OpenTelemetryMiddleware,
        )

        if not OPENTELEMETRY_AVAILABLE:
            pytest.skip("OpenTelemetry not available")

        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        # Set up a tracer provider
        trace_provider = TracerProvider()
        trace.set_tracer_provider(trace_provider)

        mcp = FastMCP("Test")
        middleware = OpenTelemetryMiddleware(propagate_context=True)
        mcp.add_middleware(middleware)

        # Track whether context was extracted
        extracted_context = []

        original_extract = middleware._extract_trace_context

        def mock_extract(context):
            result = original_extract(context)
            extracted_context.append(result)
            return result

        middleware._extract_trace_context = mock_extract  # type: ignore[method-assign]

        @mcp.tool()
        def test_tool(value: str) -> str:
            return f"result: {value}"

        async with Client(mcp) as client:
            # Call tool without trace context - should extract None
            await client.call_tool("test_tool", {"value": "test"})
            assert len(extracted_context) > 0

    async def test_context_propagation_disabled_no_injection(self):
        """Test that no context is injected when propagation is disabled."""
        from fastmcp.server.middleware.opentelemetry import (
            OPENTELEMETRY_AVAILABLE,
            OpenTelemetryMiddleware,
        )

        if not OPENTELEMETRY_AVAILABLE:
            pytest.skip("OpenTelemetry not available")

        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        # Set up a tracer provider
        trace.set_tracer_provider(TracerProvider())

        mcp = FastMCP("Test")
        mcp.add_middleware(OpenTelemetryMiddleware(propagate_context=False))

        @mcp.tool()
        def test_tool(value: str) -> str:
            return f"result: {value}"

        async with Client(mcp) as client:
            result = await client.call_tool("test_tool", {"value": "test"})
            # Check that result has no trace context metadata
            assert result.meta is None or "traceparent" not in result.meta
