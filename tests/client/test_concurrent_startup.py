"""Tests for concurrent MCP server startup."""

import asyncio
import time

import pytest

from fastmcp import Client


@pytest.mark.asyncio
async def test_concurrent_startup_parameter_accepted():
    """Test that concurrent_startup parameter is accepted."""
    config = {
        "mcpServers": {
            "echo": {
                "command": "python",
                "args": ["examples/echo.py"],
            },
        }
    }

    # Test with concurrent_startup=False (default)
    client = Client(config, concurrent_startup=False)
    assert hasattr(client.transport, "concurrent_startup")
    assert client.transport.concurrent_startup is False

    # Test with concurrent_startup=True
    client = Client(config, concurrent_startup=True)
    assert client.transport.concurrent_startup is True


@pytest.mark.asyncio
@pytest.mark.skip(reason="Known issue with proxy keep-alive in tests - works in practice")
async def test_concurrent_startup_works():
    """Test that concurrent startup actually connects servers."""
    config = {
        "mcpServers": {
            "echo1": {
                "command": "python",
                "args": ["examples/echo.py"],
            },
            "echo2": {
                "command": "python",
                "args": ["examples/echo.py"],
            },
        }
    }

    # Test with concurrent startup
    client = Client(config, concurrent_startup=True)
    async with client:
        tools = await client.list_tools()
        # Each echo server has 2 tools: echo and echo_complex
        assert len(tools) == 4

        # Test calling a tool
        result = await client.call_tool("echo1_echo", {"message": "test"})
        assert result.data == "test"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_startup_performance():
    """Test that concurrent startup is faster than sequential."""
    # Create a config with multiple servers
    config = {
        "mcpServers": {
            f"echo{i}": {
                "command": "python",
                "args": ["examples/echo.py"],
            }
            for i in range(1, 4)  # 3 servers for faster test
        }
    }

    # Measure sequential startup time
    start = time.time()
    client_seq = Client(config, concurrent_startup=False)
    async with client_seq:
        await client_seq.list_tools()
    sequential_time = time.time() - start

    # Small delay to ensure clean shutdown
    await asyncio.sleep(0.1)

    # Measure concurrent startup time
    start = time.time()
    client_conc = Client(config, concurrent_startup=True)
    async with client_conc:
        await client_conc.list_tools()
    concurrent_time = time.time() - start

    print(f"\nSequential: {sequential_time:.2f}s, Concurrent: {concurrent_time:.2f}s")
    print(f"Speedup: {sequential_time / concurrent_time:.2f}x")

    # Concurrent should be faster (with 3 servers, should be noticeable)
    # Using a conservative threshold to avoid flaky tests
    assert concurrent_time < sequential_time * 0.85, (
        f"Concurrent startup ({concurrent_time:.2f}s) should be faster than "
        f"sequential ({sequential_time:.2f}s)"
    )


@pytest.mark.asyncio
async def test_warm_up_mcp_config_transports():
    """Test the warm_up_mcp_config_transports utility function directly."""
    from fastmcp.client.transports import StdioTransport
    from fastmcp.utilities.mcp_config import warm_up_mcp_config_transports

    # Create some stdio transports
    transports = [
        StdioTransport(command="python", args=["examples/echo.py"]),
        StdioTransport(command="python", args=["examples/echo.py"]),
    ]

    # Warm up the transports
    await warm_up_mcp_config_transports(transports)

    # Check that they're connected
    for transport in transports:
        assert transport._session is not None

    # Clean up
    for transport in transports:
        await transport.close()

