"""Client timeout tests."""

import asyncio
import sys

import pytest
from mcp import McpError

from fastmcp.client import Client
from fastmcp.client.transports import (
    FastMCPTransport,
)
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


class TestTimeout:
    async def test_timeout(self, fastmcp_server: FastMCP):
        async with Client(
            transport=FastMCPTransport(fastmcp_server), timeout=0.05
        ) as client:
            with pytest.raises(
                McpError,
                match="Timed out while waiting for response to ClientRequest. Waited 0.05 seconds",
            ):
                await client.call_tool("sleep", {"seconds": 0.1})

    async def test_timeout_tool_call(self, fastmcp_server: FastMCP):
        async with Client(transport=FastMCPTransport(fastmcp_server)) as client:
            with pytest.raises(McpError):
                await client.call_tool("sleep", {"seconds": 0.1}, timeout=0.01)

    async def test_timeout_tool_call_overrides_client_timeout(
        self, fastmcp_server: FastMCP
    ):
        async with Client(
            transport=FastMCPTransport(fastmcp_server),
            timeout=2,
        ) as client:
            with pytest.raises(McpError):
                await client.call_tool("sleep", {"seconds": 0.1}, timeout=0.01)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="This test is flaky on Windows. Sometimes the client timeout is respected and sometimes it is not.",
    )
    async def test_timeout_tool_call_overrides_client_timeout_even_if_lower(
        self, fastmcp_server: FastMCP
    ):
        async with Client(
            transport=FastMCPTransport(fastmcp_server),
            timeout=0.01,
        ) as client:
            await client.call_tool("sleep", {"seconds": 0.1}, timeout=2)
