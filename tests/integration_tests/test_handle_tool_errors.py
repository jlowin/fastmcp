"""Integration tests for handle_http_errors decorator and core error handling."""

import httpx
import pytest

from fastmcp import Client, FastMCP
from fastmcp.error_handling import handle_http_errors
from fastmcp.exceptions import ToolError

pytestmark = [pytest.mark.integration, pytest.mark.timeout(15)]


def create_test_server() -> FastMCP:
    """Create a FastMCP server with tools for error handling tests."""
    mcp = FastMCP("ErrorHandlingTestServer")

    # Tools using the decorator for granular HTTP error handling
    @mcp.tool
    @handle_http_errors()
    async def async_tool_with_timeout() -> str:
        """An async tool that simulates a timeout."""
        raise httpx.TimeoutException("Connection timed out")

    @mcp.tool
    @handle_http_errors()
    def sync_tool_with_timeout() -> str:
        """A sync tool that simulates a timeout."""
        raise httpx.TimeoutException("Connection timed out")

    @mcp.tool
    @handle_http_errors()
    async def async_tool_with_404() -> dict:
        """An async tool that simulates a 404 error."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    @mcp.tool
    @handle_http_errors()
    def sync_tool_with_404() -> dict:
        """A sync tool that simulates a 404 error."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("Not Found", request=request, response=response)

    @mcp.tool
    @handle_http_errors()
    async def async_tool_with_rate_limit() -> str:
        """An async tool that simulates rate limiting."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("Rate Limited", request=request, response=response)

    @mcp.tool
    @handle_http_errors()
    async def async_tool_with_server_error() -> str:
        """An async tool that simulates a server error."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("Server Error", request=request, response=response)

    @mcp.tool
    @handle_http_errors()
    async def async_tool_with_connection_error() -> str:
        """An async tool that simulates a connection error."""
        raise httpx.ConnectError("Failed to establish connection")

    @mcp.tool
    @handle_http_errors()
    async def async_tool_success(value: str) -> str:
        """An async tool that returns successfully."""
        return f"Success: {value}"

    @mcp.tool
    @handle_http_errors()
    def sync_tool_success(value: str) -> str:
        """A sync tool that returns successfully."""
        return f"Success: {value}"

    @mcp.tool
    @handle_http_errors(mask_errors=False)
    async def async_tool_unmasked_error() -> str:
        """An async tool with unmasked internal errors."""
        raise RuntimeError("Detailed internal error info")

    @mcp.tool
    @handle_http_errors(mask_errors=True)
    async def async_tool_masked_error() -> str:
        """An async tool with masked internal errors."""
        raise RuntimeError("Sensitive details that should be hidden")

    return mcp


def create_server_with_masking() -> FastMCP:
    """Create a server with mask_error_details=True to test core error handling."""
    mcp = FastMCP("MaskedErrorServer", mask_error_details=True)

    # Tool WITHOUT decorator - tests core actionable error handling
    @mcp.tool
    async def tool_with_rate_limit_no_decorator() -> str:
        """Tool that raises 429 without decorator."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("Rate Limited", request=request, response=response)

    @mcp.tool
    async def tool_with_timeout_no_decorator() -> str:
        """Tool that raises timeout without decorator."""
        raise httpx.TimeoutException("Connection timed out")

    @mcp.tool
    async def tool_with_generic_error() -> str:
        """Tool that raises a generic error (should be masked)."""
        raise ValueError("Internal implementation detail")

    return mcp


@pytest.fixture
def test_server() -> FastMCP:
    """Create a test server for integration tests."""
    return create_test_server()


@pytest.fixture
def masked_server() -> FastMCP:
    """Create a server with error masking enabled."""
    return create_server_with_masking()


class TestDecoratorIntegration:
    """Integration tests for the handle_http_errors decorator."""

    async def test_async_tool_timeout_error(self, test_server: FastMCP):
        """Test that async tool timeout errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_timeout")

            assert "Request timed out" in str(exc_info.value)

    async def test_async_tool_404_error(self, test_server: FastMCP):
        """Test that async tool 404 errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_404")

            assert "Resource not found" in str(exc_info.value)

    async def test_async_tool_rate_limit_error(self, test_server: FastMCP):
        """Test that async tool rate limit errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_rate_limit")

            assert "Rate limit exceeded" in str(exc_info.value)

    async def test_async_tool_server_error(self, test_server: FastMCP):
        """Test that async tool server errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_server_error")

            assert "Server error" in str(exc_info.value)

    async def test_async_tool_connection_error(self, test_server: FastMCP):
        """Test that async tool connection errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_connection_error")

            assert "Network connection error" in str(exc_info.value)

    async def test_async_tool_success(self, test_server: FastMCP):
        """Test that successful async tools return values correctly."""
        async with Client(test_server) as client:
            result = await client.call_tool("async_tool_success", {"value": "test"})
            assert result.data == "Success: test"


class TestSyncToolsIntegration:
    """Integration tests for sync tools with handle_http_errors."""

    async def test_sync_tool_timeout_error(self, test_server: FastMCP):
        """Test that sync tool timeout errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("sync_tool_with_timeout")

            assert "Request timed out" in str(exc_info.value)

    async def test_sync_tool_404_error(self, test_server: FastMCP):
        """Test that sync tool 404 errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("sync_tool_with_404")

            assert "Resource not found" in str(exc_info.value)

    async def test_sync_tool_success(self, test_server: FastMCP):
        """Test that successful sync tools return values correctly."""
        async with Client(test_server) as client:
            result = await client.call_tool("sync_tool_success", {"value": "hello"})
            assert result.data == "Success: hello"


class TestMaskErrorsIntegration:
    """Integration tests for mask_errors parameter."""

    async def test_unmasked_error_shows_details(self, test_server: FastMCP):
        """Test that unmasked errors include exception details."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_unmasked_error")

            error_msg = str(exc_info.value)
            assert "Detailed internal error info" in error_msg

    async def test_masked_error_hides_details(self, test_server: FastMCP):
        """Test that masked errors hide sensitive details."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_masked_error")

            error_msg = str(exc_info.value)
            assert "An unexpected error occurred" in error_msg
            assert "Sensitive details" not in error_msg


class TestCoreActionableErrorHandling:
    """Test that core FastMCP handles actionable errors without decorator."""

    async def test_core_handles_rate_limit(self, masked_server: FastMCP):
        """Test that core error handling catches 429 even with masking."""
        async with Client(masked_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("tool_with_rate_limit_no_decorator")

            # Should get actionable message, not generic masked error
            assert "Rate limited by upstream API" in str(exc_info.value)

    async def test_core_handles_timeout(self, masked_server: FastMCP):
        """Test that core error handling catches timeouts even with masking."""
        async with Client(masked_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("tool_with_timeout_no_decorator")

            # Should get actionable message, not generic masked error
            assert "Upstream request timed out" in str(exc_info.value)

    async def test_core_masks_generic_errors(self, masked_server: FastMCP):
        """Test that generic errors are masked when mask_error_details=True."""
        async with Client(masked_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("tool_with_generic_error")

            error_msg = str(exc_info.value)
            # Should be masked
            assert "Internal implementation detail" not in error_msg
            assert "Error calling tool" in error_msg


class TestToolListingIntegration:
    """Test that decorated tools are properly listed."""

    async def test_tools_are_listed(self, test_server: FastMCP):
        """Test that all decorated tools appear in tool listing."""
        async with Client(test_server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

            # Check that our decorated tools are present
            assert "async_tool_with_timeout" in tool_names
            assert "sync_tool_with_timeout" in tool_names
            assert "async_tool_with_404" in tool_names
            assert "async_tool_success" in tool_names
            assert "sync_tool_success" in tool_names

    async def test_tool_descriptions_preserved(self, test_server: FastMCP):
        """Test that tool descriptions are preserved after decoration."""
        async with Client(test_server) as client:
            tools = await client.list_tools()
            tool_map = {t.name: t for t in tools}

            # Check descriptions are preserved
            timeout_tool = tool_map["async_tool_with_timeout"]
            assert timeout_tool.description is not None
            assert "timeout" in timeout_tool.description.lower()

            success_tool = tool_map["async_tool_success"]
            assert success_tool.description is not None
            assert "success" in success_tool.description.lower()
