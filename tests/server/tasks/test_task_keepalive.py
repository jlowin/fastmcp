"""
Tests for SEP-1686 ttl parameter handling.

Per the spec, servers MUST return ttl in all tasks/get responses,
and results should be retained for ttl milliseconds after completion.
"""

import asyncio

import pytest

from fastmcp import FastMCP
from fastmcp.client import Client


@pytest.fixture
async def keepalive_server():
    """Create a server for testing ttl behavior."""
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
    """ttl is returned in tasks/get even when task is submitted/working."""
    async with Client(keepalive_server) as client:
        # Submit task with explicit ttl
        task = await client.call_tool(
            "slow_task",
            {},
            task=True,
            ttl=30000,  # 30 seconds (client-requested)
        )

        # Check status immediately - should be submitted or working
        status = await task.status()
        assert status.status in ["submitted", "working"]

        # ttl should be present per spec (MUST return in all responses)
        # TODO: Docket uses a global execution_ttl for all tasks, not per-task TTLs.
        # The spec allows servers to override client-requested TTL (line 431).
        # FastMCP returns the server's actual global TTL (60000ms default from Docket).
        # If Docket gains per-task TTL support, update this to verify client-requested TTL is respected.
        assert status.ttl == 60000  # Server's global TTL, not client-requested 30000


async def test_keepalive_returned_in_completed_state(keepalive_server: FastMCP):
    """ttl is returned in tasks/get after task completes."""
    async with Client(keepalive_server) as client:
        # Submit and complete task
        task = await client.call_tool(
            "quick_task",
            {"value": 5},
            task=True,
            ttl=45000,  # Client-requested TTL
        )
        await task.wait(timeout=2.0)

        # Check status - should be completed
        status = await task.status()
        assert status.status == "completed"

        # TODO: Docket uses global execution_ttl, not per-task TTLs.
        # Server returns its global TTL (60000ms), not the client-requested 45000ms.
        # This is spec-compliant - servers MAY override requested TTL (spec line 431).
        assert status.ttl == 60000  # Server's global TTL, not client-requested 45000


async def test_default_keepalive_when_not_specified(keepalive_server: FastMCP):
    """Default ttl is used when client doesn't specify."""
    async with Client(keepalive_server) as client:
        # Submit without explicit ttl
        task = await client.call_tool("quick_task", {"value": 3}, task=True)
        await task.wait(timeout=2.0)

        status = await task.status()
        # Should have default ttl (60000ms = 60 seconds)
        assert status.ttl == 60000


@pytest.mark.skip(
    reason="Cannot test per-task TTL expiration - Docket uses global execution_ttl (60s default)"
)
async def test_expired_task_returns_unknown(keepalive_server: FastMCP):
    """Tasks return unknown state after ttl expires.

    This test requires per-task TTL support to verify short-lived task expiration.
    FastMCP uses Docket's global execution_ttl (60 seconds default) for all tasks.

    TODO: If Docket gains per-task TTL support, un-skip this test and verify:
    1. Client can request short TTL (e.g., 100ms)
    2. Server respects this TTL
    3. After TTL expires, tasks/get returns status="unknown"
    4. Redis automatically cleans up expired task mappings

    This is spec-compliant: servers MAY override requested TTL (spec line 431).
    FastMCP's architectural choice is to use a consistent global TTL for all tasks.
    """
    async with Client(keepalive_server) as client:
        # Submit task with very short ttl (100ms)
        task = await client.call_tool("quick_task", {"value": 7}, task=True, ttl=100)
        await task.wait(timeout=2.0)
        task_id = task.task_id

        # Task should be completed
        status = await task.status()
        assert status.status == "completed"

        # Wait for ttl to expire
        await asyncio.sleep(0.2)  # 200ms > 100ms ttl

        # Docket's TTL handles cleanup automatically, task should now be expired
        status = await client.get_task_status(task_id)
        assert status.status == "unknown"
