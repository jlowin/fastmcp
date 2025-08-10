"""Test that stdio subprocess cleanup works properly (Issue #1311)."""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from fastmcp import Client


@pytest.mark.client_process
async def test_stdio_subprocess_cleanup():
    """Test that Client properly cleans up stdio subprocesses when closed."""
    # Create a temporary MCP server file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as server_file:
        server_file.write(
            """
from fastmcp import FastMCP

mcp = FastMCP("TestServer")

@mcp.tool
def add(a: int, b: int) -> int:
    return a + b

if __name__ == "__main__":
    mcp.run()
"""
        )
        server_path = Path(server_file.name)

    try:
        # Function to count processes matching the server file
        def count_server_processes():
            try:
                result = subprocess.run(
                    ["pgrep", "-f", server_path.name],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return len(result.stdout.strip().split("\n"))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # pgrep might not be available on all systems
                pass
            return 0

        # Ensure no processes are running initially
        initial_count = count_server_processes()
        assert initial_count == 0, f"Found {initial_count} existing processes"

        # Create client with MCPConfig transport (the problematic case)
        client = Client(
            {"test-server": {"command": sys.executable, "args": [str(server_path)]}}
        )

        # Connect and verify server is running
        await client._connect()
        tools = await client.list_tools()
        assert len(tools) > 0, "Server should have tools"

        # Check that subprocess is running
        during_count = count_server_processes()
        assert during_count > 0, "Server subprocess should be running"

        # Close the client
        await client.close()

        # Give subprocess time to terminate
        await asyncio.sleep(0.5)

        # Verify subprocess was cleaned up
        after_count = count_server_processes()
        assert after_count == 0, (
            f"Server subprocess should be terminated, but {after_count} still running"
        )

    finally:
        # Clean up any remaining processes
        try:
            subprocess.run(
                ["pkill", "-f", server_path.name],
                capture_output=True,
                timeout=2,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Remove temporary file
        server_path.unlink(missing_ok=True)


@pytest.mark.client_process
async def test_mcp_config_transport_has_close_method():
    """Test that MCPConfigTransport has a close() method."""
    from fastmcp.client.transports import MCPConfigTransport

    # Create a simple config
    config = {
        "mcpServers": {
            "test": {
                "command": "echo",
                "args": ["test"],
            }
        }
    }

    transport = MCPConfigTransport(config)

    # Verify close method exists and is callable
    assert hasattr(transport, "close"), "MCPConfigTransport should have close() method"
    assert callable(transport.close), "close() should be callable"

    # Calling close on unconnected transport should not error
    await transport.close()
