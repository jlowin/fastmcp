"""Integration tests for handle_tool_errors decorator with FastMCP tools."""

import httpx
import pytest

from fastmcp import Client, FastMCP
from fastmcp.error_handling import handle_tool_errors
from fastmcp.exceptions import ToolError

pytestmark = [pytest.mark.integration, pytest.mark.timeout(15)]


def create_test_server() -> FastMCP:
    """Create a FastMCP server with tools decorated with handle_tool_errors."""
    mcp = FastMCP("ErrorHandlingTestServer")

    @mcp.tool
    @handle_tool_errors(api_name="Test API")
    async def async_tool_with_timeout() -> str:
        """An async tool that simulates a timeout."""
        raise httpx.TimeoutException("Connection timed out")

    @mcp.tool
    @handle_tool_errors(api_name="Test API")
    def sync_tool_with_timeout() -> str:
        """A sync tool that simulates a timeout."""
        raise httpx.TimeoutException("Connection timed out")

    @mcp.tool
    @handle_tool_errors(api_name="Data API")
    async def async_tool_with_404() -> dict:
        """An async tool that simulates a 404 error."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError(
            "Not Found", request=request, response=response
        )

    @mcp.tool
    @handle_tool_errors(api_name="Data API")
    def sync_tool_with_404() -> dict:
        """A sync tool that simulates a 404 error."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError(
            "Not Found", request=request, response=response
        )

    @mcp.tool
    @handle_tool_errors(api_name="External API")
    async def async_tool_with_rate_limit() -> str:
        """An async tool that simulates rate limiting."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError(
            "Rate Limited", request=request, response=response
        )

    @mcp.tool
    @handle_tool_errors(api_name="External API")
    async def async_tool_with_server_error() -> str:
        """An async tool that simulates a server error."""
        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError(
            "Server Error", request=request, response=response
        )

    @mcp.tool
    @handle_tool_errors(api_name="Network Service")
    async def async_tool_with_connection_error() -> str:
        """An async tool that simulates a connection error."""
        raise httpx.ConnectError("Failed to establish connection")

    @mcp.tool
    @handle_tool_errors(api_name="Success API")
    async def async_tool_success(value: str) -> str:
        """An async tool that returns successfully."""
        return f"Success: {value}"

    @mcp.tool
    @handle_tool_errors(api_name="Success API")
    def sync_tool_success(value: str) -> str:
        """A sync tool that returns successfully."""
        return f"Success: {value}"

    @mcp.tool
    @handle_tool_errors(mask_internal_errors=False)
    async def async_tool_unmasked_error() -> str:
        """An async tool with unmasked internal errors."""
        raise RuntimeError("Detailed internal error info")

    @mcp.tool
    @handle_tool_errors(mask_internal_errors=True)
    async def async_tool_masked_error() -> str:
        """An async tool with masked internal errors."""
        raise RuntimeError("Sensitive details that should be hidden")

    return mcp


@pytest.fixture
def test_server() -> FastMCP:
    """Create a test server for integration tests."""
    return create_test_server()


class TestAsyncToolsIntegration:
    """Integration tests for async tools with handle_tool_errors."""

    async def test_async_tool_timeout_error(self, test_server: FastMCP):
        """Test that async tool timeout errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_timeout")

            assert "Test API: Request timed out" in str(exc_info.value)

    async def test_async_tool_404_error(self, test_server: FastMCP):
        """Test that async tool 404 errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_404")

            assert "Data API: Resource not found" in str(exc_info.value)

    async def test_async_tool_rate_limit_error(self, test_server: FastMCP):
        """Test that async tool rate limit errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_rate_limit")

            assert "External API: Rate limit exceeded" in str(exc_info.value)

    async def test_async_tool_server_error(self, test_server: FastMCP):
        """Test that async tool server errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_server_error")

            assert "External API: Server error" in str(exc_info.value)

    async def test_async_tool_connection_error(self, test_server: FastMCP):
        """Test that async tool connection errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("async_tool_with_connection_error")

            expected = "Network Service: Network connection error"
            assert expected in str(exc_info.value)

    async def test_async_tool_success(self, test_server: FastMCP):
        """Test that successful async tools return values correctly."""
        async with Client(test_server) as client:
            result = await client.call_tool(
                "async_tool_success", {"value": "test"}
            )
            assert result.data == "Success: test"


class TestSyncToolsIntegration:
    """Integration tests for sync tools with handle_tool_errors."""

    async def test_sync_tool_timeout_error(self, test_server: FastMCP):
        """Test that sync tool timeout errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("sync_tool_with_timeout")

            assert "Test API: Request timed out" in str(exc_info.value)

    async def test_sync_tool_404_error(self, test_server: FastMCP):
        """Test that sync tool 404 errors reach client correctly."""
        async with Client(test_server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("sync_tool_with_404")

            assert "Data API: Resource not found" in str(exc_info.value)

    async def test_sync_tool_success(self, test_server: FastMCP):
        """Test that successful sync tools return values correctly."""
        async with Client(test_server) as client:
            result = await client.call_tool(
                "sync_tool_success", {"value": "hello"}
            )
            assert result.data == "Success: hello"


class TestMaskInternalErrorsIntegration:
    """Integration tests for mask_internal_errors parameter."""

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
