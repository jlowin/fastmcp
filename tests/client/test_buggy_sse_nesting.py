"""Tests for reproducing the bug in SSE server nested path handling."""

import pytest
from mcp.types import TextResourceContents
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import FastMCPTransport
from fastmcp.low_level.sse_server_transport import SseServerTransport


def create_event_handler(transport):
    """Create an event handler for SSE connections."""

    async def event_handler(request: Request):
        """Handle SSE event connections."""
        async with transport.connect_sse(request.scope, request.receive, request.send):  # type: ignore
            # Keep connection alive until closed by client
            await request.is_disconnected()
        return None

    return event_handler


class TestBuggySSENesting:
    """Test buggy behavior of SSE nesting (pre-fix)."""

    def _create_buggy_transport(self):
        """Simulate buggy pre-fix behavior of nested SSE transport."""
        # Create the FastMCP server
        mcp = FastMCP()

        @mcp.resource("test://hello")
        def hello_resource():
            return "Hello, world!"

        # Create the buggy transport - this simulates the pre-fix behavior
        # by intentionally modifying the original SseServerTransport

        class BuggySSEServerTransport(SseServerTransport):
            """Transport that reproduces the root_path bug in SSE transport."""

            def get_event_url(self):
                """Return buggy event URL that ignores root_path."""
                # This simulates the bug where root_path was ignored
                # Original code just returned "/events" without considering root_path
                return "/events"

        # Create a Starlette app with nested structure
        base_app = Starlette()
        nested_app = Starlette()

        # Create the buggy transport
        transport = BuggySSEServerTransport("/events")

        # Create the event handler (uses the transport's get_event_url)
        event_handler = create_event_handler(transport)

        # Add routes to the nested app
        nested_app.routes.append(
            Route("/events", endpoint=event_handler, methods=["GET"])
        )

        # Mount the nested app to the base app
        base_app.routes.append(Mount("/api", app=nested_app))

        return base_app, mcp, transport

    @pytest.mark.xfail(reason="Bug simulation - should fail with the buggy transport")
    @pytest.mark.asyncio
    async def test_buggy_sse_nesting(self):
        """
        Test that demonstrates the bug in nested SSE server handling.

        This test is expected to fail because it simulates the bug where
        the root_path was not included in the event URL, causing the client
        to connect to the wrong endpoint.
        """
        app, mcp, transport = self._create_buggy_transport()

        # Test with the client
        client = Client(transport=FastMCPTransport(mcp))

        async with client:
            # Try to access the resource - this should fail with the buggy transport
            # because the client will try to connect to "/events" instead of "/api/events"
            result = await client.read_resource("test://hello")

            # This assertion should not be reached with the buggy transport
            assert isinstance(result[0], TextResourceContents)
            assert result[0].text == "Hello, world!"
