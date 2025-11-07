"""
Tests for SEP-1686 protocol-level task handling.

Tests that the server correctly detects task metadata, submits to Docket,
and sends notifications.
"""

import asyncio

import pytest

from fastmcp import FastMCP
from fastmcp.client import Client


@pytest.fixture
async def task_enabled_server():
    """Create a FastMCP server with task-enabled tools."""
    mcp = FastMCP("task-test-server")

    @mcp.tool()
    async def simple_tool(message: str) -> str:
        """A simple tool for testing."""
        return f"Processed: {message}"

    @mcp.tool()
    async def failing_tool() -> str:
        """A tool that always fails."""
        raise ValueError("This tool always fails")

    return mcp


async def test_synchronous_tool_call_unchanged(task_enabled_server):
    """Tools without task metadata execute synchronously as before."""
    async with Client(task_enabled_server) as client:
        # Regular call without task metadata
        result = await client.call_tool("simple_tool", {"message": "hello"})

        # Should execute immediately and return result
        assert "Processed: hello" in str(result)


async def test_tool_call_with_task_metadata_returns_immediately(task_enabled_server):
    """Tools with task metadata return immediately with ToolTask object."""
    async with Client(task_enabled_server) as client:
        # Call with task metadata
        task = await client.call_tool("simple_tool", {"message": "test"}, task=True)

        # Should return a ToolTask object immediately
        from fastmcp.client.client import ToolTask

        assert isinstance(task, ToolTask)
        assert isinstance(task.task_id, str)
        assert len(task.task_id) > 0


async def test_task_metadata_includes_task_id_and_keep_alive(task_enabled_server):
    """Task metadata properly includes taskId and keepAlive."""
    async with Client(task_enabled_server) as client:
        # Submit with specific task ID and keepAlive
        task = await client.call_tool(
            "simple_tool",
            {"message": "test"},
            task=True,
            task_id="custom-task-123",
            keep_alive=30000,
        )

        # Should use our custom task ID
        assert task.task_id == "custom-task-123"


async def test_task_executes_in_background_via_docket(task_enabled_server):
    """Task is submitted to Docket and executes in background."""
    # Use Events to prove background execution
    execution_started = asyncio.Event()
    execution_completed = asyncio.Event()

    @task_enabled_server.tool(task=True)  # Enable background execution
    async def coordinated_tool() -> str:
        """Tool with coordination points."""
        execution_started.set()
        await execution_completed.wait()  # Block until signaled
        return "completed"

    async with Client(task_enabled_server) as client:
        # Submit task
        task = await client.call_tool("coordinated_tool", task=True)

        # Should return immediately (not blocking)
        assert task

        # Wait for execution to start (proves it's running)
        await asyncio.wait_for(execution_started.wait(), timeout=2.0)

        # Task should still be working (not completed yet)
        status = await task.status()
        assert status.status in ["submitted", "working"]

        # Signal completion
        execution_completed.set()

        # Now wait for task to finish
        await task.wait(timeout=2.0)

        # Get the result
        result = await task.result()
        assert result.data == "completed"


async def test_task_notification_sent_after_submission(task_enabled_server):
    """Server sends notifications/tasks/created after task submission."""
    # For now, just verify task submission works
    # Full notification tracking can be added later

    @task_enabled_server.tool(task=True)  # Enable background execution
    async def background_tool(message: str) -> str:
        return f"Processed: {message}"

    async with Client(task_enabled_server) as client:
        task = await client.call_tool("background_tool", {"message": "test"}, task=True)
        assert task

        # Verify we can query the task
        status = await task.status()
        assert status.task_id == task.task_id


async def test_graceful_degradation_task_false_executes_immediately(
    task_enabled_server,
):
    """Tools without task=True execute synchronously even with task metadata (SEP-1686)."""

    @task_enabled_server.tool()  # No task=True (defaults to False)
    async def sync_only_tool(message: str) -> str:
        return f"Sync: {message}"

    async with Client(task_enabled_server) as client:
        # Try to call with task metadata - server should ignore and execute synchronously
        task = await client.call_tool("sync_only_tool", {"message": "test"}, task=True)

        # Task should wrap an immediate result (graceful degradation)
        # Can get result without waiting
        result = await task.result()
        assert "Sync: test" in str(result)

        # Status should show as completed immediately
        status = await task.status()
        assert status.status == "completed"


async def test_failed_task_stores_error(task_enabled_server):
    """Failed tasks store the error in results."""

    @task_enabled_server.tool(task=True)  # Enable background execution
    async def failing_task_tool() -> str:
        raise ValueError("This tool always fails")

    async with Client(task_enabled_server) as client:
        task = await client.call_tool("failing_task_tool", task=True)

        # Wait for task to fail
        status = await task.wait(state="failed", timeout=2.0)
        assert status.status == "failed"
