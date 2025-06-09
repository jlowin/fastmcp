from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import mcp.types
import pytest
from pydantic import AnyUrl

from fastmcp import Client, FastMCP
from fastmcp.server.context import Context
from fastmcp.server.middleware import MCPMiddleware


@dataclass
class Recording:
    # the method is the MCP method that was called, e.g. "tools/list"
    method: str
    # the hook is the name of the hook that was called, e.g. "on_list_tools"
    hook: str
    # the type is the type of the payload, e.g. "request" or "notification"
    type: str
    payload: mcp.types.Request | mcp.types.Notification
    result: mcp.types.ServerResult | None


class RecordingMiddleware(MCPMiddleware):
    """A middleware that automatically records all method calls."""

    def __init__(self):
        self.calls: dict[str, list[Recording]] = defaultdict(list)
        super().__init__()

    def __getattribute__(self, name: str) -> Callable:
        """Dynamically create recording methods for any on_* method."""
        if name.startswith("on_"):

            async def record_and_call(arg: Any, call_next: Callable) -> Any:
                result = await call_next(arg)

                if isinstance(
                    arg, mcp.types.ServerNotification | mcp.types.ServerRequest
                ):
                    method = arg.root.method
                else:
                    method = getattr(arg, "method", "unknown")

                # Record the call
                self.calls[name].append(
                    Recording(
                        method=method,
                        hook=name,
                        type=type(arg).__name__,
                        payload=arg,
                        result=result,
                    )
                )

                return result

            return record_and_call

        return super().__getattribute__(name)

    def get_calls(
        self, method: str | None = None, hook: str | None = None
    ) -> list[Recording]:
        """
        Get all recorded calls for a specific method or hook.

        Args:
            method: The method to filter by (e.g. "tools/list")
            hook: The hook to filter by (e.g. "on_list_tools")

        Returns:
            A list of recorded calls.
        """
        calls = []
        for recordings in self.calls.values():
            for recording in recordings:
                if method and hook:
                    if recording.method == method and recording.hook == hook:
                        calls.append(recording)
                elif method:
                    if recording.method == method:
                        calls.append(recording)
                elif hook:
                    if recording.hook == hook:
                        calls.append(recording)
                else:
                    calls.append(recording)
        return calls

    def assert_called(
        self, hook: str | None = None, method: str | None = None, times: int = 1
    ):
        """Assert that a hook was called a specific number of times."""
        calls = self.get_calls(hook=hook, method=method)
        actual_times = len(calls)

        assert actual_times == times, (
            f"Expected {hook!r} to be called {times} times"
            f"{f' for method {method!r}' if method else ''}, "
            f"but was called {actual_times} times"
        )

    def reset(self):
        """Clear all recorded calls."""
        self.calls.clear()


@pytest.fixture
def recording_middleware():
    """Fixture that provides a recording middleware instance."""
    middleware = RecordingMiddleware()
    yield middleware
    middleware.reset()


@pytest.fixture
def mcp_server(recording_middleware):
    mcp = FastMCP()

    @mcp.tool
    def add(a: int, b: int) -> int:
        return a + b

    @mcp.resource("resource://test")
    def test_resource() -> str:
        return "test resource"

    @mcp.resource("resource://test-template/{x}")
    def test_resource_with_path(x: int) -> str:
        return f"test resource with {x}"

    @mcp.prompt
    def test_prompt(x: str) -> str:
        return f"test prompt with {x}"

    @mcp.tool
    async def progress_tool(context: Context) -> None:
        await context.report_progress(progress=1, total=10, message="test")

    @mcp.tool
    async def log_tool(context: Context) -> None:
        await context.info(message="test log")

    @mcp.tool
    async def sample_tool(context: Context) -> None:
        await context.sample("hello")

    mcp.add_middleware(recording_middleware)

    # Register progress handler
    @mcp._mcp_server.progress_notification()
    async def handle_progress(
        progress_token: str | int,
        progress: float,
        total: float | None,
        message: str | None,
    ):
        print("HI")

    return mcp


@pytest.fixture
def client(mcp_server: FastMCP) -> Client:
    return Client(mcp_server)


class TestMethods:
    async def test_initialize(self, client, recording_middleware):
        async with client:
            pass

        # Initialize requests are handled before the server is initialized and therefore
        # not picked up by middleware, unfortunately. However, an initialization notification IS
        # sent to the client, which does get picked up
        recording_middleware.assert_called(
            hook="on_message", method="notifications/initialized"
        )
        recording_middleware.assert_called(
            hook="on_client_notification", method="notifications/initialized"
        )
        recording_middleware.assert_called(
            hook="on_initialize_notification", method="notifications/initialized"
        )
        assert len(recording_middleware.get_calls()) == 3

    async def test_list_tools(self, client, recording_middleware):
        async with client:
            await client.list_tools()

        recording_middleware.assert_called(hook="on_message", method="tools/list")
        recording_middleware.assert_called(
            hook="on_client_request", method="tools/list"
        )
        recording_middleware.assert_called(
            hook="on_list_tools_request", method="tools/list"
        )

    async def test_list_resources(self, client, recording_middleware):
        async with client:
            await client.list_resources()

        recording_middleware.assert_called("on_message", "resources/list")
        recording_middleware.assert_called("on_client_request", "resources/list")
        recording_middleware.assert_called(
            "on_list_resources_request", "resources/list"
        )

    async def test_list_resource_templates(self, client, recording_middleware):
        async with client:
            await client.list_resource_templates()

        recording_middleware.assert_called("on_message", "resources/templates/list")
        recording_middleware.assert_called(
            "on_client_request", "resources/templates/list"
        )
        recording_middleware.assert_called(
            "on_list_resource_templates_request", "resources/templates/list"
        )

    async def test_list_prompts(self, client, recording_middleware):
        async with client:
            await client.list_prompts()

        recording_middleware.assert_called("on_message", "prompts/list")
        recording_middleware.assert_called("on_client_request", "prompts/list")
        recording_middleware.assert_called("on_list_prompts_request", "prompts/list")

    async def test_get_prompt(self, client, recording_middleware):
        async with client:
            await client.get_prompt("test_prompt", {"x": "hello"})

        recording_middleware.assert_called("on_message", "prompts/get")
        recording_middleware.assert_called("on_client_request", "prompts/get")
        recording_middleware.assert_called("on_get_prompt_request", "prompts/get")

    async def test_call_tool(self, client, recording_middleware: RecordingMiddleware):
        async with client:
            await client.call_tool("add", {"a": 1, "b": 2})

        recording_middleware.assert_called("on_message", "tools/call")
        recording_middleware.assert_called("on_client_request", "tools/call")
        recording_middleware.assert_called("on_call_tool_request", "tools/call")

        calls = recording_middleware.get_calls(hook="on_call_tool_request")
        assert len(calls) == 1
        assert isinstance(calls[0].payload, mcp.types.CallToolRequest)
        assert calls[0].payload.params.name == "add"
        assert calls[0].payload.params.arguments == {"a": 1, "b": 2}
        assert isinstance(calls[0].result.root, mcp.types.CallToolResult)  # type: ignore[attr-defined]
        assert calls[0].result.root.content[0].text == "3"  # type: ignore[attr-defined]

    async def test_read_resource(
        self, client, recording_middleware: RecordingMiddleware
    ):
        async with client:
            await client.read_resource("resource://test")

        recording_middleware.assert_called("on_message", "resources/read")
        recording_middleware.assert_called("on_client_request", "resources/read")
        recording_middleware.assert_called("on_read_resource_request", "resources/read")

        calls = recording_middleware.get_calls(hook="on_read_resource_request")
        assert len(calls) == 1
        assert isinstance(calls[0].payload, mcp.types.ReadResourceRequest)
        assert calls[0].payload.params.uri == AnyUrl("resource://test")
        assert isinstance(calls[0].result.root, mcp.types.ReadResourceResult)  # type: ignore[attr-defined]
        assert calls[0].result.root.contents[0].text == "test resource"  # type: ignore[attr-defined]

    async def test_read_resource_template(
        self, client, recording_middleware: RecordingMiddleware
    ):
        async with client:
            await client.read_resource("resource://test-template/123")

        recording_middleware.assert_called("on_message", "resources/read")
        recording_middleware.assert_called("on_client_request", "resources/read")
        recording_middleware.assert_called("on_read_resource_request", "resources/read")
        calls = recording_middleware.get_calls(hook="on_read_resource_request")
        assert len(calls) == 1
        assert isinstance(calls[0].payload, mcp.types.ReadResourceRequest)
        assert calls[0].payload.params.uri == AnyUrl("resource://test-template/123")
        assert isinstance(calls[0].result.root, mcp.types.ReadResourceResult)  # type: ignore[attr-defined]
        assert calls[0].result.root.contents[0].text == "test resource with 123"  # type: ignore[attr-defined]

    async def test_progress(
        self, mcp_server, recording_middleware: RecordingMiddleware
    ):
        async def progress_handler(
            progress: float, total: float | None, message: str | None
        ) -> None:
            pass

        async with Client(mcp_server, progress_handler=progress_handler) as client:
            await client.call_tool("progress_tool", {})

        recording_middleware.assert_called("on_message", "notifications/progress")
        recording_middleware.assert_called(
            "on_server_notification", "notifications/progress"
        )
        recording_middleware.assert_called(
            "on_progress_notification", "notifications/progress"
        )

    async def test_logging(self, mcp_server, recording_middleware: RecordingMiddleware):
        async with Client(mcp_server) as client:
            await client.call_tool("log_tool", {})

        recording_middleware.assert_called("on_message", "notifications/message")
        recording_middleware.assert_called(
            "on_server_notification", "notifications/message"
        )
        recording_middleware.assert_called(
            "on_logging_message_notification", "notifications/message"
        )


class TestMiddleware:
    async def test_multiple_calls(self, client, recording_middleware):
        async with client:
            # Call list_tools multiple times
            await client.list_tools()
            await client.list_tools()
            await client.list_tools()

        recording_middleware.assert_called(
            "on_list_tools_request", "tools/list", times=3
        )

        # Can also check the full call history
        calls = recording_middleware.get_calls(method="tools/list")
        assert len(calls) == 9  # 3 on_message + 3 on_client_request + 3 on_list_tools
