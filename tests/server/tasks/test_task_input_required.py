"""
Tests for input_required task status (SEP-1686).

This file tests:

1. **get_task_context()** - Detects if running inside a background task
2. **TaskContextInfo** - Contains task_id and session_id from execution key
3. **TaskContext** - Provides elicit() and sample() in background tasks
4. **CurrentTaskContext()** - Dependency to get TaskContext in workers
5. **input_required flow** - Status updates during elicitation/sampling

## Architecture Note

The regular ``Context`` dependency is NOT available in background tasks
because workers may run in separate processes without an MCP session.
Use ``TaskContext`` (via ``CurrentTaskContext()``) instead.
"""

import asyncio
from dataclasses import dataclass

import pytest

from fastmcp import Context, FastMCP
from fastmcp.client import Client
from fastmcp.client.elicitation import ElicitResult
from fastmcp.server.dependencies import (
    CurrentTaskContext,
    TaskContext,
    TaskContextInfo,
    get_task_context,
)
from fastmcp.server.elicitation import AcceptedElicitation, DeclinedElicitation


# =============================================================================
# Tests for get_task_context() and TaskContextInfo
# =============================================================================


def test_get_task_context_returns_none_outside_worker():
    """get_task_context() returns None when not in a Docket worker context."""
    result = get_task_context()
    assert result is None


def test_task_context_info_dataclass():
    """TaskContextInfo is a proper dataclass with expected fields."""
    ctx = TaskContextInfo(task_id="task-123", session_id="session-456")
    assert ctx.task_id == "task-123"
    assert ctx.session_id == "session-456"


async def test_task_context_detected_in_background_task():
    """get_task_context() returns TaskContextInfo inside background tasks."""
    mcp = FastMCP("task-context-test")
    captured_context = {}

    @mcp.tool(task=True)
    async def capture_task_context() -> str:
        """Background task that captures its context."""
        task_ctx = get_task_context()
        captured_context["has_context"] = task_ctx is not None
        if task_ctx:
            captured_context["task_id"] = task_ctx.task_id
            captured_context["session_id"] = task_ctx.session_id
        return "done"

    async with Client(mcp) as client:
        task = await client.call_tool("capture_task_context", {}, task=True)
        task_id = task.task_id

        # Wait for task to complete
        await task

        # Verify context was captured
        assert captured_context["has_context"] is True
        assert captured_context["task_id"] == task_id
        assert isinstance(captured_context["session_id"], str)
        assert len(captured_context["session_id"]) > 0


async def test_foreground_tool_not_in_task_context():
    """Regular foreground tools do NOT have task context."""
    mcp = FastMCP("foreground-test")
    captured_context = {}

    @dataclass
    class Name:
        name: str

    @mcp.tool  # NOT task=True
    async def foreground_with_elicit(ctx: Context) -> str:
        task_ctx = get_task_context()
        captured_context["has_context"] = task_ctx is not None
        result = await ctx.elicit(message="Name?", response_type=Name)
        if isinstance(result, AcceptedElicitation) and isinstance(result.data, Name):
            return result.data.name
        return "none"

    async def handler(message, response_type, params, ctx):
        return ElicitResult(action="accept", content=response_type(name="Alice"))

    async with Client(mcp, elicitation_handler=handler) as client:
        result = await client.call_tool("foreground_with_elicit", {})
        assert result.data == "Alice"

        # Should NOT be in task context
        assert captured_context["has_context"] is False


async def test_concurrent_tasks_have_isolated_contexts():
    """Multiple concurrent background tasks each have isolated task contexts."""
    mcp = FastMCP("concurrent-test")
    captured_ids: list[str] = []

    @mcp.tool(task=True)
    async def capture_and_delay() -> str:
        task_ctx = get_task_context()
        if task_ctx:
            captured_ids.append(task_ctx.task_id)
        await asyncio.sleep(0.01)  # Small delay for concurrency
        return "done"

    async with Client(mcp) as client:
        # Start 3 tasks concurrently
        tasks = [
            await client.call_tool("capture_and_delay", {}, task=True)
            for _ in range(3)
        ]

        # Get expected task IDs
        expected_ids = {t.task_id for t in tasks}

        # Wait for all
        await asyncio.gather(*tasks)

        # Verify all 3 unique task IDs were captured
        assert len(set(captured_ids)) == 3
        assert set(captured_ids) == expected_ids


async def test_task_context_task_id_matches_client_task():
    """TaskContextInfo.task_id matches the client-visible task ID."""
    mcp = FastMCP("task-id-match-test")
    captured_task_id = {}

    @mcp.tool(task=True)
    async def capture_id() -> str:
        task_ctx = get_task_context()
        if task_ctx:
            captured_task_id["from_worker"] = task_ctx.task_id
        return "done"

    async with Client(mcp) as client:
        task = await client.call_tool("capture_id", {}, task=True)
        captured_task_id["from_client"] = task.task_id

        await task

        # IDs should match
        assert captured_task_id["from_worker"] == captured_task_id["from_client"]


# =============================================================================
# Tests Documenting Current Limitation: Context Not Available in Tasks
# =============================================================================


async def test_context_not_available_in_background_task():
    """LIMITATION: Context dependency fails in background tasks.

    This documents the current architectural limitation. Tools with task=True
    cannot use the Context dependency because there's no active MCP session
    in the Docket worker.
    """
    mcp = FastMCP("limitation-test")

    @mcp.tool(task=True)
    async def needs_context(ctx: Context) -> str:
        # This line will never be reached - Context resolution fails
        return "unreachable"

    async with Client(mcp) as client:
        task = await client.call_tool("needs_context", {}, task=True)

        # Task fails because Context cannot be resolved in worker
        with pytest.raises(Exception, match="No active context found|ctx"):
            await task


# =============================================================================
# Tests for TaskContext and CurrentTaskContext
# =============================================================================


async def test_current_task_context_available_in_background_task():
    """CurrentTaskContext() resolves successfully in background tasks."""
    mcp = FastMCP("task-context-test")
    captured = {}

    @mcp.tool(task=True)
    async def use_task_context(task_ctx: TaskContext = CurrentTaskContext()) -> str:
        captured["task_id"] = task_ctx.task_id
        captured["session_id"] = task_ctx.session_id
        return "success"

    async with Client(mcp) as client:
        task = await client.call_tool("use_task_context", {}, task=True)
        result = await task

        assert result.data == "success"
        assert captured["task_id"] == task.task_id
        assert isinstance(captured["session_id"], str)


async def test_current_task_context_fails_in_foreground():
    """CurrentTaskContext() raises RuntimeError in foreground tools."""
    mcp = FastMCP("foreground-error-test")

    @mcp.tool  # NOT task=True
    async def foreground_with_task_ctx(
        task_ctx: TaskContext = CurrentTaskContext(),
    ) -> str:
        return "unreachable"

    async with Client(mcp) as client:
        with pytest.raises(Exception, match="Failed to resolve dependency|background"):
            await client.call_tool("foreground_with_task_ctx", {})


async def test_task_context_elicit_accepts_user_input():
    """TaskContext.elicit() successfully receives user input in background task."""
    mcp = FastMCP("elicit-test")

    @dataclass
    class UserName:
        name: str

    @mcp.tool(task=True)
    async def ask_name(task_ctx: TaskContext = CurrentTaskContext()) -> str:
        result = await task_ctx.elicit(
            message="What is your name?",
            response_type=UserName,
        )
        if isinstance(result, AcceptedElicitation):
            return f"Hello, {result.data.name}!"
        return "No name provided"

    async def elicitation_handler(message, response_type, params, ctx):
        return ElicitResult(action="accept", content=response_type(name="Alice"))

    async with Client(mcp, elicitation_handler=elicitation_handler) as client:
        task = await client.call_tool("ask_name", {}, task=True)
        result = await task

        assert result.data == "Hello, Alice!"


async def test_task_context_elicit_handles_decline():
    """TaskContext.elicit() handles declined responses."""
    mcp = FastMCP("elicit-decline-test")

    @mcp.tool(task=True)
    async def ask_something(task_ctx: TaskContext = CurrentTaskContext()) -> str:
        result = await task_ctx.elicit(
            message="Please provide input",
            response_type=str,
        )
        if isinstance(result, DeclinedElicitation):
            return "User declined"
        return "Unexpected"

    async def decline_handler(message, response_type, params, ctx):
        return ElicitResult(action="decline", content=None)

    async with Client(mcp, elicitation_handler=decline_handler) as client:
        task = await client.call_tool("ask_something", {}, task=True)
        result = await task

        assert result.data == "User declined"


async def test_task_context_elicit_with_structured_type():
    """TaskContext.elicit() works with structured response types."""
    mcp = FastMCP("structured-elicit-test")

    @dataclass
    class NumberInput:
        value: int

    @mcp.tool(task=True)
    async def ask_number(task_ctx: TaskContext = CurrentTaskContext()) -> str:
        result = await task_ctx.elicit(
            message="Enter a number:",
            response_type=NumberInput,
        )
        if isinstance(result, AcceptedElicitation):
            return f"You entered: {result.data.value}"
        return "No number"

    async def number_handler(message, response_type, params, ctx):
        return ElicitResult(action="accept", content=response_type(value=42))

    async with Client(mcp, elicitation_handler=number_handler) as client:
        task = await client.call_tool("ask_number", {}, task=True)
        result = await task

        assert result.data == "You entered: 42"


async def test_task_context_sample_calls_client():
    """TaskContext.sample() makes sampling requests through the client."""
    mcp = FastMCP("sample-test")
    sampling_called = {}

    @mcp.tool(task=True)
    async def summarize(
        text: str, task_ctx: TaskContext = CurrentTaskContext()
    ) -> str:
        result = await task_ctx.sample(
            messages=[{"role": "user", "content": f"Summarize: {text}"}],
            max_tokens=100,
        )
        return result.content.text

    async def sampling_handler(messages, params, context):
        from mcp.types import CreateMessageResult, TextContent

        sampling_called["messages"] = messages
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text="This is a summary."),
            model="test-model",
        )

    async with Client(mcp, sampling_handler=sampling_handler) as client:
        task = await client.call_tool(
            "summarize", {"text": "A long document..."}, task=True
        )
        result = await task

        assert result.data == "This is a summary."
        assert sampling_called.get("messages") is not None


async def test_task_context_properties():
    """TaskContext exposes task_id and session_id properties."""
    mcp = FastMCP("properties-test")
    captured = {}

    @mcp.tool(task=True)
    async def check_properties(
        task_ctx: TaskContext = CurrentTaskContext(),
    ) -> str:
        captured["task_id"] = task_ctx.task_id
        captured["session_id"] = task_ctx.session_id
        # Both should be non-empty strings
        assert isinstance(task_ctx.task_id, str)
        assert len(task_ctx.task_id) > 0
        assert isinstance(task_ctx.session_id, str)
        assert len(task_ctx.session_id) > 0
        return "verified"

    async with Client(mcp) as client:
        task = await client.call_tool("check_properties", {}, task=True)
        result = await task

        assert result.data == "verified"
        # task_id from TaskContext should match client's task_id
        assert captured["task_id"] == task.task_id


async def test_task_context_elicit_updates_status():
    """TaskContext.elicit() updates task status to input_required during wait.

    This test verifies the SEP-1686 flow where the task status transitions:
    working -> input_required (during elicit) -> working (after response)
    """
    mcp = FastMCP("status-update-test")

    @dataclass
    class TextInput:
        text: str

    @mcp.tool(task=True)
    async def track_status_elicit(
        task_ctx: TaskContext = CurrentTaskContext(),
    ) -> str:
        result = await task_ctx.elicit(
            message="Input needed",
            response_type=TextInput,
        )
        if isinstance(result, AcceptedElicitation):
            return result.data.text
        return "declined"

    async def delayed_handler(message, response_type, params, ctx):
        # Small delay to allow status observation
        await asyncio.sleep(0.05)
        return ElicitResult(action="accept", content=response_type(text="test-value"))

    async with Client(mcp, elicitation_handler=delayed_handler) as client:
        task = await client.call_tool("track_status_elicit", {}, task=True)

        # The task completes with the elicited value
        result = await task
        assert result.data == "test-value"
