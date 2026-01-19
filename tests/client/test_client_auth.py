"""Client authentication tests."""

import asyncio

import pytest
from mcp.client.auth import OAuthClientProvider

from fastmcp.client import Client
from fastmcp.client.auth.bearer import BearerAuth
from fastmcp.client.transports import (
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
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


class TestAuth:
    def test_default_auth_is_none(self):
        client = Client(transport=StreamableHttpTransport("http://localhost:8000"))
        assert client.transport.auth is None

    def test_stdio_doesnt_support_auth(self):
        with pytest.raises(ValueError, match="This transport does not support auth"):
            Client(transport=StdioTransport("echo", ["hello"]), auth="oauth")

    def test_oauth_literal_sets_up_oauth_shttp(self):
        client = Client(
            transport=StreamableHttpTransport("http://localhost:8000"), auth="oauth"
        )
        assert isinstance(client.transport, StreamableHttpTransport)
        assert isinstance(client.transport.auth, OAuthClientProvider)

    def test_oauth_literal_pass_direct_to_transport(self):
        client = Client(
            transport=StreamableHttpTransport("http://localhost:8000", auth="oauth"),
        )
        assert isinstance(client.transport, StreamableHttpTransport)
        assert isinstance(client.transport.auth, OAuthClientProvider)

    def test_oauth_literal_sets_up_oauth_sse(self):
        client = Client(transport=SSETransport("http://localhost:8000"), auth="oauth")
        assert isinstance(client.transport, SSETransport)
        assert isinstance(client.transport.auth, OAuthClientProvider)

    def test_oauth_literal_pass_direct_to_transport_sse(self):
        client = Client(transport=SSETransport("http://localhost:8000", auth="oauth"))
        assert isinstance(client.transport, SSETransport)
        assert isinstance(client.transport.auth, OAuthClientProvider)

    def test_auth_string_sets_up_bearer_auth_shttp(self):
        client = Client(
            transport=StreamableHttpTransport("http://localhost:8000"),
            auth="test_token",
        )
        assert isinstance(client.transport, StreamableHttpTransport)
        assert isinstance(client.transport.auth, BearerAuth)
        assert client.transport.auth.token.get_secret_value() == "test_token"

    def test_auth_string_pass_direct_to_transport_shttp(self):
        client = Client(
            transport=StreamableHttpTransport(
                "http://localhost:8000", auth="test_token"
            ),
        )
        assert isinstance(client.transport, StreamableHttpTransport)
        assert isinstance(client.transport.auth, BearerAuth)
        assert client.transport.auth.token.get_secret_value() == "test_token"

    def test_auth_string_sets_up_bearer_auth_sse(self):
        client = Client(
            transport=SSETransport("http://localhost:8000"),
            auth="test_token",
        )
        assert isinstance(client.transport, SSETransport)
        assert isinstance(client.transport.auth, BearerAuth)
        assert client.transport.auth.token.get_secret_value() == "test_token"

    def test_auth_string_pass_direct_to_transport_sse(self):
        client = Client(
            transport=SSETransport("http://localhost:8000", auth="test_token"),
        )
        assert isinstance(client.transport, SSETransport)
        assert isinstance(client.transport.auth, BearerAuth)
        assert client.transport.auth.token.get_secret_value() == "test_token"
