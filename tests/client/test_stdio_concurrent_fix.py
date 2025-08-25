"""Tests for the stdio transport concurrent initialization fix."""

import asyncio
import inspect
import tempfile
from pathlib import Path

import pytest

from fastmcp.client import Client
from fastmcp.client.transports import PythonStdioTransport


@pytest.mark.asyncio
async def test_stdio_transport_concurrent_connection():
    """Test that StdioTransport can handle concurrent connection attempts.

    This test verifies the fix for issue #1625 where parallel calls to
    stdio MCP servers would fail with "Received request before initialization
    was complete" errors due to a race condition in the connection logic.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create a simple test server script
        server_script = inspect.cleandoc("""
            from fastmcp import FastMCP

            mcp = FastMCP()

            @mcp.tool
            def add(a: int, b: int) -> int:
                return a + b

            if __name__ == '__main__':
                mcp.run()
            """)

        script_path = tmp_path / "test_server.py"
        script_path.write_text(server_script)

        # Test with direct stdio transport - this should work with our fix
        transport = PythonStdioTransport(script_path)
        client = Client(transport)

        async with client:
            # Test with 50 parallel calls - this would fail before the fix
            tasks = [client.call_tool("add", {"a": i, "b": 1}) for i in range(50)]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            exceptions = [result for result in results if isinstance(result, Exception)]

            # Should have no exceptions with our fix
            assert len(exceptions) == 0, (
                f"Found {len(exceptions)} exceptions: {[str(e) for e in exceptions[:5]]}"
            )

            # All successful results should be correct
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) == 50
            for i, result in enumerate(successful_results):
                assert result.data == i + 1  # a=i, b=1, so result should be i+1
