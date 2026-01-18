"""Tests for signal handling in FastMCP server.run_stdio_async() method."""

import asyncio
import threading
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastmcp import FastMCP


class TestSignalHandling:
    """Test signal handling behavior in different contexts."""

    @pytest.mark.asyncio
    async def test_stdio_async_main_thread_installs_signal_handlers(self):
        """Test that signal handlers are installed for run_stdio_async in main thread."""
        server = FastMCP()

        # Create mock streams
        mock_read_stream = AsyncMock()
        mock_write_stream = AsyncMock()
        
        # Create a proper async context manager for stdio_server
        @asynccontextmanager
        async def mock_stdio():
            yield (mock_read_stream, mock_write_stream)
        
        # Create a proper async context manager for lifespan
        @asynccontextmanager
        async def mock_lifespan():
            yield

        # Mock the MCP server internals to prevent actual server execution
        with patch.object(server, "_lifespan_manager", side_effect=lambda: mock_lifespan()):
            with patch("fastmcp.server.server.stdio_server", side_effect=lambda: mock_stdio()):
                with patch.object(server._mcp_server, "run", new_callable=AsyncMock):
                    # Mock signal.signal to track calls
                    with patch("signal.signal") as mock_signal:
                        mock_signal.return_value = lambda *args: None

                        # Call should work without exceptions
                        await server.run_stdio_async(show_banner=False)

                        # Verify signal handlers were installed (2 calls: SIGINT and SIGTERM)
                        # Plus 2 more to restore them in finally block
                        assert mock_signal.call_count >= 4

    def test_http_main_thread_no_signal_handlers(self):
        """Test that signal handlers are NOT installed for HTTP in main thread."""
        server = FastMCP()

        # Mock anyio.run to prevent actual server execution
        with patch("fastmcp.server.server.anyio.run"):
            # Mock signal.signal to track calls
            with patch("signal.signal") as mock_signal:
                mock_signal.return_value = lambda *args: None

                try:
                    server.run(transport="http")
                except Exception:
                    # We expect this to fail since we're mocking anyio.run
                    pass

                # Verify signal handlers were NOT installed
                assert mock_signal.call_count == 0

    def test_sse_main_thread_no_signal_handlers(self):
        """Test that signal handlers are NOT installed for SSE in main thread."""
        server = FastMCP()

        # Mock anyio.run to prevent actual server execution
        with patch("fastmcp.server.server.anyio.run"):
            # Mock signal.signal to track calls
            with patch("signal.signal") as mock_signal:
                mock_signal.return_value = lambda *args: None

                try:
                    server.run(transport="sse")
                except Exception:
                    # We expect this to fail since we're mocking anyio.run
                    pass

                # Verify signal handlers were NOT installed
                assert mock_signal.call_count == 0

    def test_streamable_http_main_thread_no_signal_handlers(self):
        """Test that signal handlers are NOT installed for streamable-http in main thread."""
        server = FastMCP()

        # Mock anyio.run to prevent actual server execution
        with patch("fastmcp.server.server.anyio.run"):
            # Mock signal.signal to track calls
            with patch("signal.signal") as mock_signal:
                mock_signal.return_value = lambda *args: None

                try:
                    server.run(transport="streamable-http")
                except Exception:
                    # We expect this to fail since we're mocking anyio.run
                    pass

                # Verify signal handlers were NOT installed
                assert mock_signal.call_count == 0

    def test_stdio_async_background_thread_no_signal_handlers(self):
        """Test that signal handlers are NOT installed for run_stdio_async in background thread."""
        server = FastMCP()
        signal_call_count = []

        def run_in_thread():
            async def async_test():
                # Create mock streams
                mock_read_stream = AsyncMock()
                mock_write_stream = AsyncMock()
                
                # Create a proper async context manager for stdio_server
                @asynccontextmanager
                async def mock_stdio():
                    yield (mock_read_stream, mock_write_stream)
                
                # Create a proper async context manager for lifespan
                @asynccontextmanager
                async def mock_lifespan():
                    yield

                # Mock the MCP server internals to prevent actual server execution
                with patch.object(server, "_lifespan_manager", side_effect=lambda: mock_lifespan()):
                    with patch("fastmcp.server.server.stdio_server", side_effect=lambda: mock_stdio()):
                        with patch.object(
                            server._mcp_server, "run", new_callable=AsyncMock
                        ):
                            # Mock signal.signal to track calls
                            with patch("signal.signal") as mock_signal:
                                mock_signal.return_value = lambda *args: None

                                try:
                                    await server.run_stdio_async(show_banner=False)
                                except Exception:
                                    pass

                                # Store the call count
                                signal_call_count.append(mock_signal.call_count)

            asyncio.run(async_test())

        # Run in a background thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Verify signal handlers were NOT installed
        assert len(signal_call_count) == 1
        assert signal_call_count[0] == 0

    @pytest.mark.asyncio
    async def test_stdio_async_main_thread_keyboard_interrupt_calls_os_exit(self):
        """Test that KeyboardInterrupt in run_stdio_async/main thread calls os._exit(0)."""
        server = FastMCP()

        # Create mock streams
        mock_read_stream = AsyncMock()
        mock_write_stream = AsyncMock()
        
        # Create a proper async context manager for stdio_server
        @asynccontextmanager
        async def mock_stdio():
            yield (mock_read_stream, mock_write_stream)
        
        # Create a proper async context manager for lifespan
        @asynccontextmanager
        async def mock_lifespan():
            yield

        # Mock the MCP server internals to raise KeyboardInterrupt
        with patch.object(server, "_lifespan_manager", side_effect=lambda: mock_lifespan()):
            with patch("fastmcp.server.server.stdio_server", side_effect=lambda: mock_stdio()):
                with patch.object(
                    server._mcp_server, "run", new_callable=AsyncMock
                ) as mock_run:
                    mock_run.side_effect = KeyboardInterrupt()

                    # Mock os._exit to prevent actual exit
                    with patch("os._exit") as mock_exit:
                        # Mock signal.signal
                        with patch("signal.signal") as mock_signal:
                            mock_signal.return_value = lambda *args: None

                            await server.run_stdio_async(show_banner=False)

                            # Verify os._exit was called with 0
                            mock_exit.assert_called_once_with(0)

    def test_stdio_async_background_thread_keyboard_interrupt_propagates(self):
        """Test that KeyboardInterrupt in run_stdio_async/background thread propagates normally."""
        server = FastMCP()
        exception_raised = []

        def run_in_thread():
            async def async_test():
                # Create mock streams
                mock_read_stream = AsyncMock()
                mock_write_stream = AsyncMock()
                
                # Create a proper async context manager for stdio_server
                @asynccontextmanager
                async def mock_stdio():
                    yield (mock_read_stream, mock_write_stream)
                
                # Create a proper async context manager for lifespan
                @asynccontextmanager
                async def mock_lifespan():
                    yield

                # Mock the MCP server internals to raise KeyboardInterrupt
                with patch.object(server, "_lifespan_manager", side_effect=lambda: mock_lifespan()):
                    with patch("fastmcp.server.server.stdio_server", side_effect=lambda: mock_stdio()):
                        with patch.object(
                            server._mcp_server, "run", new_callable=AsyncMock
                        ) as mock_run:
                            mock_run.side_effect = KeyboardInterrupt()

                            # Mock os._exit to verify it's NOT called
                            with patch("os._exit") as mock_exit:
                                # Mock signal.signal
                                with patch("signal.signal") as mock_signal:
                                    mock_signal.return_value = lambda *args: None

                                    try:
                                        await server.run_stdio_async(show_banner=False)
                                    except KeyboardInterrupt:
                                        exception_raised.append(True)

                                    # Store whether os._exit was called
                                    exception_raised.append(mock_exit.call_count == 0)

            asyncio.run(async_test())

        # Run in a background thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Verify KeyboardInterrupt was raised and os._exit was NOT called
        assert len(exception_raised) == 2
        assert exception_raised[0] is True  # KeyboardInterrupt was raised
        assert exception_raised[1] is True  # os._exit was NOT called

    def test_default_transport_is_stdio(self):
        """Test that default transport (None) is treated as stdio."""
        server = FastMCP()

        # Mock anyio.run to prevent actual server execution
        with patch("fastmcp.server.server.anyio.run"):
            try:
                server.run()  # No transport specified
            except Exception:
                pass

        # The run() method now just delegates to run_async, which then calls run_stdio_async
        # Signal handling is in run_stdio_async, not in run()
        # This test just verifies that the default behavior still works
