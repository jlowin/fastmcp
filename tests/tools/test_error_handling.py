"""Unit tests for the handle_http_errors decorator."""

import httpx
import pytest
from httpx import Request, Response

from fastmcp.error_handling import handle_http_errors
from fastmcp.exceptions import ToolError


class TestHTTPStatusErrorMapping:
    """Test httpx.HTTPStatusError mappings for different status codes."""

    def _make_status_error(self, status_code: int) -> httpx.HTTPStatusError:
        """Create an HTTPStatusError with the given status code."""
        request = Request("GET", "https://api.example.com/test")
        response = Response(status_code, request=request)
        return httpx.HTTPStatusError(
            f"HTTP {status_code}", request=request, response=response
        )

    async def test_404_error(self):
        """Test that 404 status maps to 'Resource not found'."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(404)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Resource not found" in str(exc_info.value)

    async def test_429_error(self):
        """Test that 429 status maps to rate limit message."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(429)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Rate limit exceeded" in str(exc_info.value)

    async def test_500_error(self):
        """Test that 500 status maps to server error message."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(500)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Server error" in str(exc_info.value)

    async def test_502_error(self):
        """Test that 502 status maps to server error message."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(502)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Server error" in str(exc_info.value)

    async def test_503_error(self):
        """Test that 503 status maps to server error message."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(503)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Server error" in str(exc_info.value)

    async def test_401_error(self):
        """Test that 401 status shows authentication failed message."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(401)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Authentication failed or missing credentials" in str(exc_info.value)

    async def test_403_error(self):
        """Test that 403 status shows access denied message."""

        @handle_http_errors()
        async def tool():
            raise self._make_status_error(403)

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Access denied - insufficient permissions" in str(exc_info.value)


class TestTimeoutExceptionMapping:
    """Test httpx.TimeoutException mapping."""

    async def test_timeout_exception(self):
        """Test that TimeoutException maps to timeout message."""

        @handle_http_errors()
        async def tool():
            raise httpx.TimeoutException("Connection timed out")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Request timed out" in str(exc_info.value)

    async def test_connect_timeout(self):
        """Test that ConnectTimeout (subclass) maps to timeout message."""

        @handle_http_errors()
        async def tool():
            raise httpx.ConnectTimeout("Connection timed out")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Request timed out" in str(exc_info.value)

    async def test_read_timeout(self):
        """Test that ReadTimeout (subclass) maps to timeout message."""

        @handle_http_errors()
        async def tool():
            raise httpx.ReadTimeout("Read timed out")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Request timed out" in str(exc_info.value)


class TestRequestErrorMapping:
    """Test httpx.RequestError mapping."""

    async def test_request_error(self):
        """Test that RequestError maps to network connection message."""

        @handle_http_errors()
        async def tool():
            raise httpx.RequestError("Network error")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Network connection error" in str(exc_info.value)

    async def test_connect_error(self):
        """Test ConnectError (subclass) maps to network message."""

        @handle_http_errors()
        async def tool():
            raise httpx.ConnectError("Failed to connect")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert "Network connection error" in str(exc_info.value)


class TestGenericExceptionMapping:
    """Test generic exception handling with mask_errors."""

    async def test_generic_exception_masked(self):
        """Test that generic exceptions are masked by default."""

        @handle_http_errors()
        async def tool():
            raise ValueError("Sensitive internal error details")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        error_msg = str(exc_info.value)
        assert "An unexpected error occurred" in error_msg
        assert "Sensitive internal error details" not in error_msg

    async def test_generic_exception_unmasked(self):
        """Test generic exceptions show details when unmasked."""

        @handle_http_errors(mask_errors=False)
        async def tool():
            raise ValueError("Error details here")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        error_msg = str(exc_info.value)
        assert "An unexpected error occurred: Error details here" in error_msg


class TestSyncAsyncSupport:
    """Test that decorator works with both sync and async functions."""

    async def test_async_function(self):
        """Test decorator works with async functions."""

        @handle_http_errors()
        async def async_tool() -> str:
            raise httpx.TimeoutException("timeout")

        with pytest.raises(ToolError) as exc_info:
            await async_tool()

        assert "Request timed out" in str(exc_info.value)

    def test_sync_function(self):
        """Test decorator works with sync functions."""

        @handle_http_errors()
        def sync_tool() -> str:
            raise httpx.TimeoutException("timeout")

        with pytest.raises(ToolError) as exc_info:
            sync_tool()

        assert "Request timed out" in str(exc_info.value)

    async def test_async_function_success(self):
        """Test that successful async functions return normally."""

        @handle_http_errors()
        async def async_tool() -> str:
            return "success"

        result = await async_tool()
        assert result == "success"

    def test_sync_function_success(self):
        """Test that successful sync functions return normally."""

        @handle_http_errors()
        def sync_tool() -> str:
            return "success"

        result = sync_tool()
        assert result == "success"


class TestFunctionMetadataPreservation:
    """Test that function metadata is preserved by the decorator."""

    async def test_preserves_name(self):
        """Test that decorated function preserves __name__."""

        @handle_http_errors()
        async def my_custom_tool():
            """My custom docstring."""
            pass

        assert my_custom_tool.__name__ == "my_custom_tool"

    async def test_preserves_docstring(self):
        """Test that decorated function preserves __doc__."""

        @handle_http_errors()
        async def my_custom_tool():
            """This is my custom docstring for testing."""
            pass

        expected_doc = "This is my custom docstring for testing."
        assert my_custom_tool.__doc__ == expected_doc

    def test_sync_preserves_name(self):
        """Test that decorated sync function preserves __name__."""

        @handle_http_errors()
        def my_sync_tool():
            """Sync tool docstring."""
            pass

        assert my_sync_tool.__name__ == "my_sync_tool"

    def test_sync_preserves_docstring(self):
        """Test that decorated sync function preserves __doc__."""

        @handle_http_errors()
        def my_sync_tool():
            """This is my sync tool docstring."""
            pass

        assert my_sync_tool.__doc__ == "This is my sync tool docstring."


class TestToolErrorPassthrough:
    """Test that ToolError raised by the user is passed through unchanged."""

    async def test_tool_error_passthrough_async(self):
        """Test that ToolError from async function passes through."""

        @handle_http_errors()
        async def tool():
            raise ToolError("Custom user error message")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        # Should be the exact message, not wrapped
        assert str(exc_info.value) == "Custom user error message"

    def test_tool_error_passthrough_sync(self):
        """Test that ToolError from sync function passes through."""

        @handle_http_errors()
        def tool():
            raise ToolError("Custom user error message")

        with pytest.raises(ToolError) as exc_info:
            tool()

        # Should be the exact message, not wrapped
        assert str(exc_info.value) == "Custom user error message"


class TestExceptionChaining:
    """Test that original exceptions are chained properly."""

    async def test_exception_chained(self):
        """Test that original exception is available via __cause__."""

        @handle_http_errors()
        async def tool():
            raise ValueError("Original error")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert str(exc_info.value.__cause__) == "Original error"

    async def test_httpx_exception_chained(self):
        """Test that httpx exceptions are chained properly."""

        @handle_http_errors()
        async def tool():
            raise httpx.TimeoutException("Connection timed out")

        with pytest.raises(ToolError) as exc_info:
            await tool()

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, httpx.TimeoutException)
