import logging
import warnings
from unittest.mock import MagicMock, Mock, patch

import pytest
from mcp.types import ModelPreferences
from starlette.requests import Request

from fastmcp.client import Client
from fastmcp.server.context import (
    Context,
    _map_mcp_to_python_level,
    _parse_model_preferences,
)
from fastmcp.server.server import FastMCP


class TestContextDeprecations:
    def test_get_http_request_deprecation_warning(self):
        """Test that using Context.get_http_request() raises a deprecation warning."""
        # Create a mock FastMCP instance
        mock_fastmcp = MagicMock()
        context = Context(fastmcp=mock_fastmcp)

        # Patch the dependency function to return a mock request
        mock_request = MagicMock(spec=Request)
        with patch(
            "fastmcp.server.dependencies.get_http_request", return_value=mock_request
        ):
            # Check that the deprecation warning is raised
            with pytest.warns(
                DeprecationWarning, match="Context.get_http_request\\(\\) is deprecated"
            ):
                request = context.get_http_request()

            # Verify the function still works and returns the request
            assert request is mock_request

    def test_get_http_request_deprecation_message(self):
        """Test that the deprecation warning has the correct message with guidance."""
        # Create a mock FastMCP instance
        mock_fastmcp = MagicMock()
        context = Context(fastmcp=mock_fastmcp)

        # Patch the dependency function to return a mock request
        mock_request = MagicMock(spec=Request)
        with patch(
            "fastmcp.server.dependencies.get_http_request", return_value=mock_request
        ):
            # Capture and check the specific warning message
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                context.get_http_request()

                assert len(w) == 1
                warning = w[0]
                assert issubclass(warning.category, DeprecationWarning)
                assert "Context.get_http_request() is deprecated" in str(
                    warning.message
                )
                assert (
                    "Use get_http_request() from fastmcp.server.dependencies instead"
                    in str(warning.message)
                )
                assert "https://gofastmcp.com/servers/context#http-requests" in str(
                    warning.message
                )


@pytest.fixture
def context():
    return Context(fastmcp=FastMCP())


class TestParseModelPreferences:
    def test_parse_model_preferences_string(self, context):
        mp = _parse_model_preferences("claude-3-sonnet")
        assert isinstance(mp, ModelPreferences)
        assert mp.hints is not None
        assert mp.hints[0].name == "claude-3-sonnet"

    def test_parse_model_preferences_list(self, context):
        mp = _parse_model_preferences(["claude-3-sonnet", "claude"])
        assert isinstance(mp, ModelPreferences)
        assert mp.hints is not None
        assert [h.name for h in mp.hints] == ["claude-3-sonnet", "claude"]

    def test_parse_model_preferences_object(self, context):
        obj = ModelPreferences(hints=[])
        assert _parse_model_preferences(obj) is obj

    def test_parse_model_preferences_invalid_type(self, context):
        with pytest.raises(ValueError):
            _parse_model_preferences(model_preferences=123)  # pyright: ignore[reportArgumentType] # type: ignore[invalid-argument-type]


class TestSessionId:
    def test_session_id_with_http_headers(self, context):
        """Test that session_id returns the value from mcp-session-id header."""
        from mcp.server.lowlevel.server import request_ctx
        from mcp.shared.context import RequestContext

        mock_headers = {"mcp-session-id": "test-session-123"}

        token = request_ctx.set(
            RequestContext(  # type: ignore[arg-type]
                request_id=0,
                meta=None,
                session=MagicMock(wraps={}),
                lifespan_context=MagicMock(),
                request=MagicMock(headers=mock_headers),
            )
        )

        assert context.session_id == "test-session-123"

        request_ctx.reset(token)

    def test_session_id_without_http_headers(self, context):
        """Test that session_id returns a UUID string when no HTTP headers are available."""
        import uuid

        from mcp.server.lowlevel.server import request_ctx
        from mcp.shared.context import RequestContext

        token = request_ctx.set(
            RequestContext(  # type: ignore[arg-type]
                request_id=0,
                meta=None,
                session=MagicMock(wraps={}),
                lifespan_context=MagicMock(),
            )
        )

        assert uuid.UUID(context.session_id)

        request_ctx.reset(token)


class TestContextState:
    """Test suite for Context state functionality."""

    @pytest.mark.asyncio
    async def test_context_state(self):
        """Test that state modifications in child contexts don't affect parent."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            assert context.get_state("test1") is None
            assert context.get_state("test2") is None
            context.set_state("test1", "value")
            context.set_state("test2", 2)
            assert context.get_state("test1") == "value"
            assert context.get_state("test2") == 2
            context.set_state("test1", "new_value")
            assert context.get_state("test1") == "new_value"

    @pytest.mark.asyncio
    async def test_context_state_inheritance(self):
        """Test that child contexts inherit parent state."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context1:
            context1.set_state("key1", "key1-context1")
            context1.set_state("key2", "key2-context1")
            async with Context(fastmcp=mock_fastmcp) as context2:
                # Override one key
                context2.set_state("key1", "key1-context2")
                assert context2.get_state("key1") == "key1-context2"
                assert context1.get_state("key1") == "key1-context1"
                assert context2.get_state("key2") == "key2-context1"

                async with Context(fastmcp=mock_fastmcp) as context3:
                    # Verify state was inherited
                    assert context3.get_state("key1") == "key1-context2"
                    assert context3.get_state("key2") == "key2-context1"

                    # Add a new key and verify parents were not affected
                    context3.set_state("key-context3-only", 1)
                    assert context1.get_state("key-context3-only") is None
                    assert context2.get_state("key-context3-only") is None
                    assert context3.get_state("key-context3-only") == 1

            assert context1.get_state("key1") == "key1-context1"
            assert context1.get_state("key-context3-only") is None


class TestMapMcpToPythonLevel:
    """Test suite for MCP to Python log level mapping."""

    def test_debug_level(self):
        """Test debug level mapping."""
        assert _map_mcp_to_python_level("debug") == logging.DEBUG

    def test_info_level(self):
        """Test info level mapping."""
        assert _map_mcp_to_python_level("info") == logging.INFO

    def test_notice_level(self):
        """Test notice level mapping (maps to INFO)."""
        assert _map_mcp_to_python_level("notice") == logging.INFO

    def test_warning_level(self):
        """Test warning level mapping."""
        assert _map_mcp_to_python_level("warning") == logging.WARNING

    def test_error_level(self):
        """Test error level mapping."""
        assert _map_mcp_to_python_level("error") == logging.ERROR

    def test_critical_level(self):
        """Test critical level mapping."""
        assert _map_mcp_to_python_level("critical") == logging.CRITICAL

    def test_alert_level(self):
        """Test alert level mapping (maps to CRITICAL)."""
        assert _map_mcp_to_python_level("alert") == logging.CRITICAL

    def test_emergency_level(self):
        """Test emergency level mapping (maps to CRITICAL)."""
        assert _map_mcp_to_python_level("emergency") == logging.CRITICAL

    def test_unknown_level(self):
        """Test unknown level defaults to INFO."""
        assert _map_mcp_to_python_level("unknown") == logging.INFO  # type: ignore[arg-type]


class TestContextLogging:
    """Test suite for Context logging with log_to parameter."""

    async def test_log_to_client_only_default(self):
        """Test that default behavior sends only to client, not to server logger."""
        mcp = FastMCP("test")

        @mcp.tool()
        async def test_tool(ctx: Context) -> str:
            await ctx.info("Test message")
            return "done"

        with patch("fastmcp.server.context.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            async with Client(mcp) as client:
                await client.call_tool("test_tool", {})

            # get_logger should NOT be called with default behavior
            mock_get_logger.assert_not_called()

    async def test_log_to_client_and_server(self):
        """Test that CLIENT_AND_SERVER sends to both client and server logger."""
        mcp = FastMCP("test")

        @mcp.tool()
        async def test_tool(ctx: Context) -> str:
            await ctx.info("Test message", log_to="CLIENT_AND_SERVER")
            return "done"

        with patch("fastmcp.server.context.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            async with Client(mcp) as client:
                await client.call_tool("test_tool", {})

            # Logger should be called with CLIENT_AND_SERVER
            mock_get_logger.assert_called_once_with("server.context")
            mock_logger.log.assert_called_once_with(
                logging.INFO, "Test message", extra=None
            )

    async def test_log_to_client_and_server_with_levels(self):
        """Test that different log levels work with CLIENT_AND_SERVER."""
        mcp = FastMCP("test")

        @mcp.tool()
        async def test_tool(ctx: Context) -> str:
            await ctx.debug("Debug message", log_to="CLIENT_AND_SERVER")
            await ctx.info("Info message", log_to="CLIENT_AND_SERVER")
            await ctx.warning("Warning message", log_to="CLIENT_AND_SERVER")
            await ctx.error("Error message", log_to="CLIENT_AND_SERVER")
            return "done"

        with patch("fastmcp.server.context.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            async with Client(mcp) as client:
                await client.call_tool("test_tool", {})

            # Logger should be called for all levels
            assert mock_logger.log.call_count == 4
            calls = mock_logger.log.call_args_list
            assert calls[0][0] == (logging.DEBUG, "Debug message")
            assert calls[1][0] == (logging.INFO, "Info message")
            assert calls[2][0] == (logging.WARNING, "Warning message")
            assert calls[3][0] == (logging.ERROR, "Error message")

    async def test_log_to_client_and_server_with_custom_logger(self):
        """Test that custom logger names are used when logging to server."""
        mcp = FastMCP("test")

        @mcp.tool()
        async def test_tool(ctx: Context) -> str:
            await ctx.info(
                "Custom logger message",
                logger_name="custom.logger",
                log_to="CLIENT_AND_SERVER",
            )
            return "done"

        with patch("fastmcp.server.context.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            async with Client(mcp) as client:
                await client.call_tool("test_tool", {})

            # Logger should be called with custom logger name
            mock_get_logger.assert_called_once_with("custom.logger")
            mock_logger.log.assert_called_once_with(
                logging.INFO, "Custom logger message", extra=None
            )

    async def test_log_to_client_and_server_with_extra(self):
        """Test that extra fields are passed to server logger."""
        mcp = FastMCP("test")

        @mcp.tool()
        async def test_tool(ctx: Context) -> str:
            await ctx.info(
                "Message with extra",
                extra={"key": "value", "number": 42},
                log_to="CLIENT_AND_SERVER",
            )
            return "done"

        with patch("fastmcp.server.context.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            async with Client(mcp) as client:
                await client.call_tool("test_tool", {})

            # Logger should be called with extra dict
            mock_logger.log.assert_called_once_with(
                logging.INFO, "Message with extra", extra={"key": "value", "number": 42}
            )

    async def test_log_method_with_explicit_level(self):
        """Test that log() method with explicit level works with CLIENT_AND_SERVER."""
        mcp = FastMCP("test")

        @mcp.tool()
        async def test_tool(ctx: Context) -> str:
            await ctx.log("Critical log", level="critical", log_to="CLIENT_AND_SERVER")
            return "done"

        with patch("fastmcp.server.context.get_logger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            async with Client(mcp) as client:
                await client.call_tool("test_tool", {})

            # Logger should be called with CRITICAL level
            mock_logger.log.assert_called_once_with(
                logging.CRITICAL, "Critical log", extra=None
            )
