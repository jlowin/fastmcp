"""Tests for deeply nested SSE server paths and root path handling."""

import pytest
from mcp.types import TextResourceContents
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
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


class TestDeepSSENesting:
    """Test deeply nested SSE server paths."""

    def _create_nested_app(self, depth=3):
        """Create a deeply nested Starlette app structure."""
        # Create the FastMCP server
        mcp = FastMCP()

        @mcp.resource("test://hello")
        def hello_resource():
            return "Hello, world!"

        # Create the base Starlette app
        base_app = Starlette()

        # Create the transport
        transport = SseServerTransport("/events")

        # Create the event handler
        event_handler = create_event_handler(transport)

        # Create the deepest level app first
        current_app = Starlette(
            routes=[
                Route("/events", endpoint=event_handler, methods=["GET"]),
                Route(
                    "/check",
                    endpoint=lambda req: JSONResponse({"status": "ok"}),
                    methods=["GET"],
                ),
            ]
        )

        # Create nested apps - each level mounting the previous level
        for i in range(depth - 1, 0, -1):
            parent_app = Starlette(routes=[Mount(f"/level{i}", app=current_app)])
            current_app = parent_app

        # Mount the nested structure to the base app
        base_app.routes.append(Mount("/api", app=current_app))

        return base_app, mcp, transport

    @pytest.mark.asyncio
    async def test_very_deep_nesting(self):
        """Test that root_path is correctly included even with deep nesting."""
        app, mcp, transport = self._create_nested_app(depth=5)

        # Test with the client
        client = Client(transport=FastMCPTransport(mcp))

        async with client:
            # Try to access the resource
            result = await client.read_resource("test://hello")

            # Verify we got the expected response
            assert isinstance(result[0], TextResourceContents)
            assert result[0].text == "Hello, world!"

    @pytest.mark.asyncio
    async def test_transport_with_special_chars_in_path(self):
        """Test that SSE transport works with special characters in the path."""
        # Create the FastMCP server
        mcp = FastMCP()

        @mcp.resource("test://hello")
        def hello_resource():
            return "Hello, world!"

        # Create a Starlette app with special chars in the path
        app = Starlette()

        # Create the transport
        transport = SseServerTransport("/events")

        # Create the event handler
        event_handler = create_event_handler(transport)

        # Create an app with special characters in the path
        special_app = Starlette(
            routes=[
                Route("/events", endpoint=event_handler, methods=["GET"]),
            ]
        )

        # Mount with special characters in the path
        app.routes.append(Mount("/api/special-chars", app=special_app))

        # Test with the client
        client = Client(transport=FastMCPTransport(mcp))

        async with client:
            # Try to access the resource
            result = await client.read_resource("test://hello")

            # Verify we got the expected response
            assert isinstance(result[0], TextResourceContents)
            assert result[0].text == "Hello, world!"
