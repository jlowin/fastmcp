"""Client session and task error propagation tests."""

import asyncio

import pytest

from fastmcp.client import Client
from fastmcp.server.server import FastMCP


@pytest.fixture
def fastmcp_server():
    """Fixture that creates a FastMCP server with tools, resources, and prompts."""
    server = FastMCP("TestServer")

    # Add a tool
    @server.tool
    def greet(name: str) -> str:
        """Greet someone by name."""
        return f"Hello, {name}!"

    # Add a second tool
    @server.tool
    def add(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b

    @server.tool
    async def sleep(seconds: float) -> str:
        """Sleep for a given number of seconds."""
        await asyncio.sleep(seconds)
        return f"Slept for {seconds} seconds"

    # Add a resource (return JSON string for proper typing)
    @server.resource(uri="data://users")
    async def get_users() -> str:
        import json

        return json.dumps(["Alice", "Bob", "Charlie"], separators=(",", ":"))

    # Add a resource template (return JSON string for proper typing)
    @server.resource(uri="data://user/{user_id}")
    async def get_user(user_id: str) -> str:
        import json

        return json.dumps(
            {"id": user_id, "name": f"User {user_id}", "active": True},
            separators=(",", ":"),
        )

    # Add a prompt
    @server.prompt
    def welcome(name: str) -> str:
        """Example greeting prompt."""
        return f"Welcome to FastMCP, {name}!"

    return server


@pytest.fixture
def tagged_resources_server():
    """Fixture that creates a FastMCP server with tagged resources and templates."""
    import json

    server = FastMCP("TaggedResourcesServer")

    # Add a resource with tags
    @server.resource(
        uri="data://tagged", tags={"test", "metadata"}, description="A tagged resource"
    )
    async def get_tagged_data() -> str:
        return json.dumps({"type": "tagged_data"}, separators=(",", ":"))

    # Add a resource template with tags
    @server.resource(
        uri="template://{id}",
        tags={"template", "parameterized"},
        description="A tagged template",
    )
    async def get_template_data(id: str) -> str:
        return json.dumps({"id": id, "type": "template_data"}, separators=(",", ":"))

    return server


class TestSessionTaskErrorPropagation:
    """Tests for ensuring session task errors propagate to client calls.

    Regression tests for https://github.com/jlowin/fastmcp/issues/2595
    where the client would hang indefinitely when the session task failed
    (e.g., due to HTTP 4xx/5xx errors) instead of raising an exception.
    """

    async def test_session_task_error_propagates_to_call(self, fastmcp_server):
        """Test that errors in session task propagate to pending client calls.

        When the session task fails (e.g., due to HTTP errors), pending
        client operations should immediately receive the exception rather
        than hanging indefinitely.
        """
        client = Client(fastmcp_server)

        async with client:
            original_task = client._session_state.session_task
            assert original_task is not None

            async def never_complete():
                """A coroutine that will never complete normally."""
                await asyncio.sleep(1000)

            async def failing_session():
                """Simulates a session task that raises an error."""
                raise ValueError("Simulated HTTP error")

            # Replace session_task with one that will fail
            client._session_state.session_task = asyncio.create_task(failing_session())

            # The monitoring should detect the session task failure
            with pytest.raises(ValueError, match="Simulated HTTP error"):
                await client._await_with_session_monitoring(never_complete())

            # Restore original task for cleanup
            client._session_state.session_task = original_task

    async def test_session_task_already_done_with_error(self, fastmcp_server):
        """Test that if session task is already done with error, calls fail immediately."""
        client = Client(fastmcp_server)

        async with client:
            original_task = client._session_state.session_task

            async def raise_error():
                raise ValueError("Session failed")

            # Replace session_task with one that has already failed
            failed_task = asyncio.create_task(raise_error())
            try:
                await failed_task
            except ValueError:
                pass  # Expected
            client._session_state.session_task = failed_task

            # New calls should fail immediately with the original error
            async def simple_coro():
                return "should not reach"

            with pytest.raises(ValueError, match="Session failed"):
                await client._await_with_session_monitoring(simple_coro())

            # Restore original task for cleanup
            client._session_state.session_task = original_task

    async def test_session_task_already_done_no_error_raises_runtime_error(
        self, fastmcp_server
    ):
        """Test that if session task completes without error, raises RuntimeError."""
        client = Client(fastmcp_server)

        async with client:
            original_task = client._session_state.session_task

            # Create a task that completes normally (unexpected for session task)
            completed_task = asyncio.create_task(asyncio.sleep(0))
            await completed_task
            client._session_state.session_task = completed_task

            async def simple_coro():
                return "should not reach"

            with pytest.raises(
                RuntimeError, match="Session task completed unexpectedly"
            ):
                await client._await_with_session_monitoring(simple_coro())

            # Restore original task for cleanup
            client._session_state.session_task = original_task

    async def test_normal_operation_unaffected(self, fastmcp_server):
        """Test that normal operation is unaffected by the monitoring."""
        client = Client(fastmcp_server)

        async with client:
            # These should all work normally
            tools = await client.list_tools()
            assert len(tools) > 0

            result = await client.call_tool("greet", {"name": "Test"})
            assert "Hello, Test!" in str(result.content)

            resources = await client.list_resources()
            assert len(resources) > 0

            prompts = await client.list_prompts()
            assert len(prompts) > 0

    async def test_no_session_task_falls_back_to_direct_await(self, fastmcp_server):
        """Test that when no session task exists, it falls back to direct await."""
        client = Client(fastmcp_server)

        async with client:
            # Temporarily remove session_task to test fallback
            original_task = client._session_state.session_task
            client._session_state.session_task = None

            # Should work via direct await
            async def simple_coro():
                return "success"

            result = await client._await_with_session_monitoring(simple_coro())
            assert result == "success"

            # Restore for cleanup
            client._session_state.session_task = original_task
