"""Tests for signal handling in FastMCP server signal handling methods."""

import threading
from unittest.mock import patch

from fastmcp import FastMCP


class TestSignalHandling:
    """Test signal handling behavior in different contexts."""

    def test_run_stdio_main_thread_installs_signal_handlers(self):
        """Test that run_stdio() installs signal handlers in main thread."""
        server = FastMCP()

        # Mock anyio.run to prevent actual server execution
        with patch("fastmcp.server.server.anyio.run"):
            # Mock signal.signal to track calls
            with patch("signal.signal") as mock_signal:
                mock_signal.return_value = lambda *args: None

                # Call should work without exceptions
                try:
                    server.run_stdio(show_banner=False)
                except SystemExit:
                    pass  # os._exit() will be caught

                # Verify signal handlers were installed (2 calls: SIGINT and SIGTERM)
                # Plus 2 more to restore them in finally block
                assert mock_signal.call_count >= 2

    def test_stdio_main_thread_installs_signal_handlers(self):
        """Test that signal handlers are installed for stdio in main thread via .run()."""
        server = FastMCP()

        # Mock anyio.run to prevent actual server execution
        with patch("fastmcp.server.server.anyio.run"):
            # Mock signal.signal to track calls
            with patch("signal.signal") as mock_signal:
                mock_signal.return_value = lambda *args: None

                # Call should work without exceptions
                try:
                    server.run(transport="stdio", show_banner=False)
                except SystemExit:
                    pass  # os._exit() will be caught

                # Verify signal handlers were installed (2 calls: SIGINT and SIGTERM)
                # Plus 2 more to restore them in finally block
                assert mock_signal.call_count >= 2

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

    def test_stdio_background_thread_no_signal_handlers(self):
        """Test that signal handlers are NOT installed for stdio in background thread via .run()."""
        server = FastMCP()
        signal_call_count = []

        def run_in_thread():
            # Mock anyio.run to prevent actual server execution
            with patch("fastmcp.server.server.anyio.run"):
                # Mock signal.signal to track calls
                with patch("signal.signal") as mock_signal:
                    mock_signal.return_value = lambda *args: None

                    try:
                        server.run(transport="stdio", show_banner=False)
                    except Exception:
                        pass

                    # Store the call count
                    signal_call_count.append(mock_signal.call_count)

        # Run in a background thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Verify signal handlers were NOT installed
        assert len(signal_call_count) == 1
        assert signal_call_count[0] == 0

    def test_stdio_main_thread_keyboard_interrupt_calls_os_exit(self):
        """Test that KeyboardInterrupt in .run() for stdio calls os._exit(0)."""
        server = FastMCP()

        # Mock anyio.run to raise KeyboardInterrupt
        with patch("fastmcp.server.server.anyio.run") as mock_anyio:
            mock_anyio.side_effect = KeyboardInterrupt()

            # Mock os._exit to prevent actual exit
            with patch("os._exit") as mock_exit:
                # Mock signal.signal
                with patch("signal.signal") as mock_signal:
                    mock_signal.return_value = lambda *args: None

                    server.run(transport="stdio", show_banner=False)

                    # Verify os._exit was called with 0
                    mock_exit.assert_called_once_with(0)

    def test_stdio_background_thread_keyboard_interrupt_propagates(self):
        """Test that KeyboardInterrupt in .run()/background thread propagates normally."""
        server = FastMCP()
        exception_raised = []

        def run_in_thread():
            # Mock anyio.run to raise KeyboardInterrupt
            with patch("fastmcp.server.server.anyio.run") as mock_anyio:
                mock_anyio.side_effect = KeyboardInterrupt()

                # Mock os._exit to verify it's NOT called
                with patch("os._exit") as mock_exit:
                    # Mock signal.signal
                    with patch("signal.signal") as mock_signal:
                        mock_signal.return_value = lambda *args: None

                        try:
                            server.run(transport="stdio", show_banner=False)
                        except KeyboardInterrupt:
                            exception_raised.append(True)

                        # Store whether os._exit was called
                        exception_raised.append(mock_exit.call_count == 0)

        # Run in a background thread
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Verify KeyboardInterrupt was raised and os._exit was NOT called
        assert len(exception_raised) == 2
        assert exception_raised[0] is True  # KeyboardInterrupt was raised
        assert exception_raised[1] is True  # os._exit was NOT called

    def test_default_transport_is_stdio(self):
        """Test that default transport (None) is treated as stdio and gets signal handlers."""
        server = FastMCP()

        # Mock run_stdio to prevent actual server execution
        with patch.object(server, "run_stdio") as mock_run_stdio:
            try:
                server.run()  # No transport specified - should default to stdio
            except Exception:
                pass

            # Verify run_stdio was called (since default is stdio)
            mock_run_stdio.assert_called_once()
