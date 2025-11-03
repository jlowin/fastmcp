"""
Tests for client-side task methods.

Tests the client's call_tool_as_task, get_task_status, and get_task_result methods.
"""

import asyncio

import pytest

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.utilities.tests import temporary_settings


@pytest.fixture(autouse=True)
def enable_docket_and_tasks():
    """Enable Docket and task protocol support for all client task tests."""
    with temporary_settings(
        experimental__enable_docket=True,
        experimental__enable_tasks=True,
    ):
        # Verify both are enabled
        import fastmcp

        assert fastmcp.settings.experimental.enable_docket, (
            "Docket should be enabled after fixture"
        )
        assert fastmcp.settings.experimental.enable_tasks, (
            "Tasks should be enabled after fixture"
        )
        yield


@pytest.fixture
async def task_server():
    """Create a test server with background tasks."""
    mcp = FastMCP("client-test-server")

    @mcp.tool(task=True)  # Enable background execution
    async def echo(message: str) -> str:
        """Echo back the message."""
        return f"Echo: {message}"

    @mcp.tool(task=True)  # Enable background execution
    async def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    return mcp


async def test_call_tool_as_task_returns_task_object(task_server):
    """call_tool_as_task returns a ToolTask object."""
    async with Client(task_server) as client:
        task = await client.call_tool_as_task("echo", {"message": "hello"})

        from fastmcp.client.client import ToolTask

        assert isinstance(task, ToolTask)
        assert isinstance(task.task_id, str)
        assert len(task.task_id) > 0


async def test_call_tool_as_task_with_custom_task_id(task_server):
    """call_tool_as_task accepts custom task ID."""
    async with Client(task_server) as client:
        custom_id = "my-custom-task-123"
        task = await client.call_tool_as_task(
            "echo", {"message": "test"}, task_id=custom_id
        )

        assert task.task_id == custom_id


async def test_call_tool_as_task_with_custom_keep_alive(task_server):
    """call_tool_as_task accepts custom keepAlive."""
    async with Client(task_server) as client:
        task = await client.call_tool_as_task(
            "echo",
            {"message": "test"},
            keep_alive=120000,  # 2 minutes
        )

        # Task should be created with custom keepAlive
        # This will be tracked in the server
        assert task is not None


async def test_task_status_method_returns_status(task_server):
    """Task.status() returns TaskStatusResponse."""
    async with Client(task_server) as client:
        task = await client.call_tool_as_task("echo", {"message": "test"})

        status = await task.status()

        assert status.task_id == task.task_id
        assert status.status in ["submitted", "working", "completed"]


async def test_task_result_method_returns_tool_result(task_server):
    """Task.result() returns CallToolResult with tool data."""
    async with Client(task_server) as client:
        task = await client.call_tool_as_task("multiply", {"a": 6, "b": 7})

        # Verify task accepted for background execution
        assert not task.returned_immediately, "Task should execute in background"

        # Get result (waits automatically)
        result = await task.result()
        assert result.data == 42


async def test_end_to_end_task_flow(task_server):
    """Complete end-to-end flow: submit, poll, retrieve."""
    # Use Event to create a controlled delay
    start_signal = asyncio.Event()
    complete_signal = asyncio.Event()

    @task_server.tool(task=True)  # Enable background execution
    async def controlled_tool(message: str) -> str:
        """Tool with controlled execution."""
        start_signal.set()
        await complete_signal.wait()
        return f"Processed: {message}"

    async with Client(task_server) as client:
        # Submit task
        task = await client.call_tool_as_task(
            "controlled_tool", {"message": "integration test"}
        )

        # Wait for execution to start
        await asyncio.wait_for(start_signal.wait(), timeout=2.0)

        # Check status while running
        status = await task.status()
        assert status.status in ["submitted", "working"]

        # Signal completion
        complete_signal.set()

        # Wait for task to finish and retrieve result
        result = await task.result()
        assert result.data == "Processed: integration test"


async def test_multiple_concurrent_tasks(task_server):
    """Multiple tasks can run concurrently."""
    async with Client(task_server) as client:
        # Submit multiple tasks
        tasks = []
        for i in range(5):
            task = await client.call_tool_as_task("multiply", {"a": i, "b": 2})
            tasks.append((task, i * 2))

        # Wait for all to complete and verify results
        for task, expected in tasks:
            result = await task.result()
            assert result.data == expected


async def test_task_id_auto_generation(task_server):
    """Task IDs are auto-generated if not provided."""
    async with Client(task_server) as client:
        # Submit without custom task ID
        task_1 = await client.call_tool_as_task("echo", {"message": "first"})
        task_2 = await client.call_tool_as_task("echo", {"message": "second"})

        # Should generate different IDs
        assert task_1.task_id != task_2.task_id
        assert len(task_1.task_id) > 0
        assert len(task_2.task_id) > 0


async def test_task_await_syntax(task_server):
    """Tasks can be awaited directly to get result."""
    async with Client(task_server) as client:
        task = await client.call_tool_as_task("multiply", {"a": 7, "b": 6})

        # Can await task directly (syntactic sugar for task.result())
        result = await task
        assert result.data == 42
