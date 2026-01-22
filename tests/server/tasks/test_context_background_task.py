"""Tests for Context background task support (SEP-1686)."""

import pytest

from fastmcp import FastMCP
from fastmcp.server.context import Context


class TestContextBackgroundTaskSupport:
    """Tests for Context.is_background_task and related functionality."""

    def test_context_not_background_task_by_default(self):
        """Context should not be a background task by default."""
        mcp = FastMCP("test")
        ctx = Context(mcp)
        assert ctx.is_background_task is False
        assert ctx.task_id is None

    def test_context_is_background_task_when_task_id_provided(self):
        """Context should be a background task when task_id is provided."""
        mcp = FastMCP("test")
        ctx = Context(mcp, task_id="test-task-123")
        assert ctx.is_background_task is True
        assert ctx.task_id == "test-task-123"

    def test_context_task_id_is_readonly(self):
        """task_id should be a read-only property."""
        mcp = FastMCP("test")
        ctx = Context(mcp, task_id="test-task-123")
        with pytest.raises(AttributeError):
            ctx.task_id = "new-id"  # type: ignore[misc]


class TestContextElicitBackgroundTask:
    """Tests for Context.elicit() in background task mode."""

    @pytest.mark.asyncio
    async def test_elicit_raises_when_background_task_but_no_docket(self):
        """elicit() should raise when in background task mode but Docket unavailable."""
        mcp = FastMCP("test")
        ctx = Context(mcp, task_id="test-task-123")

        # Set up minimal session mock
        class MockSession:
            _fastmcp_state_prefix = "test-session"

        ctx._session = MockSession()  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="Docket"):
            await ctx.elicit("Need input", str)


class TestContextDocumentation:
    """Tests to verify Context documentation and API surface."""

    def test_is_background_task_has_docstring(self):
        """is_background_task property should have documentation."""
        assert Context.is_background_task.__doc__ is not None
        assert "background task" in Context.is_background_task.__doc__.lower()

    def test_task_id_has_docstring(self):
        """task_id property should have documentation."""
        assert Context.task_id.fget.__doc__ is not None  # type: ignore[union-attr]
        assert "task ID" in Context.task_id.fget.__doc__  # type: ignore[union-attr]
