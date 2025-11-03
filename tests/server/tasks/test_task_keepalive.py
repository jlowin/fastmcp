"""
Tests for SEP-1686 keepAlive parameter handling.

Per the spec, servers MUST return keepAlive in all tasks/get responses,
and results should be retained for keepAlive milliseconds after completion.
"""

import asyncio

import pytest

from fastmcp import FastMCP
from fastmcp.client import Client


@pytest.fixture
async def keepalive_server():
    """Create a server for testing keepAlive behavior."""
    mcp = FastMCP("keepalive-test")

    @mcp.tool(task=True)
    async def quick_task(value: int) -> int:
        return value * 2

    @mcp.tool(task=True)
    async def slow_task() -> str:
        await asyncio.sleep(1)
        return "done"

    return mcp


async def test_keepalive_returned_in_submitted_state(keepalive_server: FastMCP):
    """keepAlive is returned in tasks/get even when task is submitted/working."""
    async with Client(keepalive_server) as client:
        # Submit task with explicit keepAlive
        task = await client.call_tool_as_task(
            "slow_task",
            {},
            keep_alive=30000,  # 30 seconds
        )

        # Check status immediately - should be submitted or working
        status = await task.status()
        assert status.status in ["submitted", "working"]

        # keepAlive should be present per spec (MUST return in all responses)
        assert status.keep_alive == 30000


async def test_keepalive_returned_in_completed_state(keepalive_server: FastMCP):
    """keepAlive is returned in tasks/get after task completes."""
    async with Client(keepalive_server) as client:
        # Submit and complete task
        task = await client.call_tool_as_task(
            "quick_task", {"value": 5}, keep_alive=45000
        )
        await task.wait(timeout=2.0)

        # Check status - should be completed
        status = await task.status()
        assert status.status == "completed"
        assert status.keep_alive == 45000


async def test_default_keepalive_when_not_specified(keepalive_server: FastMCP):
    """Default keepAlive is used when client doesn't specify."""
    async with Client(keepalive_server) as client:
        # Submit without explicit keepAlive
        task = await client.call_tool_as_task("quick_task", {"value": 3})
        await task.wait(timeout=2.0)

        status = await task.status()
        # Should have default keepAlive (60000ms = 60 seconds)
        assert status.keep_alive == 60000


async def test_expired_task_returns_unknown(keepalive_server: FastMCP):
    """Tasks return unknown state after keepAlive expires."""
    async with Client(keepalive_server) as client:
        # Submit task with very short keepAlive (100ms)
        task = await client.call_tool_as_task(
            "quick_task", {"value": 7}, keep_alive=100
        )
        await task.wait(timeout=2.0)
        task_id = task.task_id

        # Task should be completed
        status = await task.status()
        assert status.status == "completed"

        # Wait for keepAlive to expire
        await asyncio.sleep(0.2)  # 200ms > 100ms keepAlive

        # Manually trigger cleanup (in production this would be automatic)
        from fastmcp.client.transports import FastMCPTransport

        if isinstance(client.transport, FastMCPTransport):
            from fastmcp.server.tasks._temporary_docket_shims import cleanup_expired

            await cleanup_expired()

        # Task should now return unknown (expired and cleaned up)
        status = await client.get_task_status(task_id)
        assert status.status == "unknown"
