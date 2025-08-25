"""Test for stdio proxy race condition fix."""

import asyncio
import inspect
import tempfile
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import PythonStdioTransport


class TestProxyStdioRaceFix:
    """Test that the proxy stdio race condition is fixed."""

    async def test_proxy_parallel_calls_no_race_condition(self):
        """Test that parallel calls through stdio proxy don't fail with race conditions."""

        # Create a temporary script for the backend server
        server_script = inspect.cleandoc("""
            from fastmcp import FastMCP

            mcp = FastMCP()

            @mcp.tool
            def add(a: int, b: int) -> int:
                return a + b

            if __name__ == '__main__':
                mcp.run()
            """)

        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "test.py"
            script_path.write_text(server_script)

            # Set up the backend client (stdio transport)
            backend_client = Client(
                transport=PythonStdioTransport(script_path=script_path)
            )

            # Create proxy server
            proxy = FastMCP.as_proxy(backend=backend_client, name="test_parallel_calls")

            # Create client that connects to the proxy
            client = Client(transport=proxy)

            # Test with enough parallel calls to trigger race condition
            count = 20

            tasks = [client.list_tools() for _ in range(count)]

            async with backend_client, client:
                results = await asyncio.gather(*tasks, return_exceptions=True)

            # All calls should succeed
            exceptions = [result for result in results if isinstance(result, Exception)]
            successes = [
                result for result in results if not isinstance(result, Exception)
            ]

            assert len(exceptions) == 0, (
                f"Got {len(exceptions)} exceptions: {exceptions}"
            )
            assert len(successes) == count
            assert all(
                len(result) == 1 for result in successes
            )  # Each should have 1 tool (add)

    async def test_proxy_parallel_tool_calls_no_race_condition(self):
        """Test that parallel tool calls through stdio proxy don't fail with race conditions."""

        # Create a temporary script for the backend server
        server_script = inspect.cleandoc("""
            from fastmcp import FastMCP

            mcp = FastMCP()

            @mcp.tool
            def add(a: int, b: int) -> int:
                return a + b

            if __name__ == '__main__':
                mcp.run()
            """)

        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "test.py"
            script_path.write_text(server_script)

            # Set up the backend client (stdio transport)
            backend_client = Client(
                transport=PythonStdioTransport(script_path=script_path)
            )

            # Create proxy server
            proxy = FastMCP.as_proxy(backend=backend_client, name="test_parallel_calls")

            # Create client that connects to the proxy
            client = Client(transport=proxy)

            # Test with parallel tool calls
            count = 15

            tasks = [
                client.call_tool("add", {"a": i, "b": i + 1}) for i in range(count)
            ]

            async with backend_client, client:
                results = await asyncio.gather(*tasks, return_exceptions=True)

            # All calls should succeed
            exceptions = [result for result in results if isinstance(result, Exception)]
            successes = [
                result for result in results if not isinstance(result, Exception)
            ]

            assert len(exceptions) == 0, (
                f"Got {len(exceptions)} exceptions: {exceptions}"
            )
            assert len(successes) == count

            # Verify results are correct
            for i, result in enumerate(successes):
                expected = i + (i + 1)  # a + b where a=i, b=i+1
                assert result.data == expected, (
                    f"Expected {expected}, got {result.data}"
                )
