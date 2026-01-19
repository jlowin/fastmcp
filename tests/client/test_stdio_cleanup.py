"""
Test for issue #2792: Event loop is closed warning during subprocess transport cleanup.

This test attempts to reproduce the warning that appears on Linux/CI when using
StdioTransport with pytest. The issue is that asyncio's BaseSubprocessTransport.__del__
tries to use the event loop after it's been closed by pytest-asyncio.

The warning looks like:
    PytestUnraisableExceptionWarning: Exception ignored in:
        <function BaseSubprocessTransport.__del__ at ...>
    RuntimeError: Event loop is closed

See: https://github.com/jlowin/fastmcp/issues/2792
"""

import asyncio
import gc
import inspect

import pytest

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport


@pytest.fixture
def simple_server_script(tmp_path):
    """Create a minimal MCP server script."""
    script = inspect.cleandoc("""
        from fastmcp import FastMCP

        mcp = FastMCP()

        @mcp.tool
        def echo(message: str) -> str:
            return message

        if __name__ == "__main__":
            mcp.run()
    """)
    script_file = tmp_path / "simple_server.py"
    script_file.write_text(script)
    return script_file


class TestStdioCleanup:
    """Test suite for stdio transport cleanup issues."""

    @pytest.mark.timeout(30)
    @pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
    async def test_stdio_transport_cleanup_no_warning(self, simple_server_script):
        """Test that stdio transport doesn't produce event loop warnings on cleanup.

        This test fails if a PytestUnraisableExceptionWarning is raised during
        cleanup, which happens when BaseSubprocessTransport.__del__ tries to
        use a closed event loop.
        """
        transport = PythonStdioTransport(
            script_path=simple_server_script, keep_alive=False
        )
        client = Client(transport=transport)

        async with client:
            result = await client.call_tool("echo", {"message": "test"})
            assert result.data == "test"

        # The warning typically appears after the test completes and the event
        # loop is closed, then GC runs. We can try to force it by:
        # 1. Explicitly deleting references
        del client
        del transport

        # 2. Running GC while the loop is still open
        gc.collect()

        # 3. Yielding to let any pending callbacks run
        await asyncio.sleep(0.1)

    @pytest.mark.timeout(30)
    @pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
    async def test_stdio_transport_with_keep_alive_cleanup(self, simple_server_script):
        """Test that keep_alive=True also cleans up properly when explicitly closed."""
        transport = PythonStdioTransport(
            script_path=simple_server_script, keep_alive=True
        )
        client = Client(transport=transport)

        async with client:
            result = await client.call_tool("echo", {"message": "test"})
            assert result.data == "test"

        # Explicitly close even though keep_alive=True
        await client.close()

        del client
        del transport
        gc.collect()
        await asyncio.sleep(0.1)

    @pytest.mark.timeout(30)
    @pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
    async def test_direct_disconnect_then_gc(self, simple_server_script):
        """Test explicit disconnect followed by GC."""
        transport = PythonStdioTransport(
            script_path=simple_server_script, keep_alive=True
        )

        await transport.connect()
        await transport.disconnect()

        # Try to force any lingering references to be collected
        del transport
        gc.collect()
        await asyncio.sleep(0.1)
