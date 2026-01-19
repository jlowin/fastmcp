"""Client transport inference tests."""

import asyncio

import pytest

from fastmcp.client.transports import (
    FastMCPTransport,
    MCPConfigTransport,
    SSETransport,
    StdioTransport,
    StreamableHttpTransport,
    infer_transport,
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


class TestInferTransport:
    """Tests for the infer_transport function."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/api/sse/stream",
            "https://localhost:8080/mcp/sse/endpoint",
            "http://example.com/api/sse",
            "http://example.com/api/sse/",
            "https://localhost:8080/mcp/sse/",
            "http://example.com/api/sse?param=value",
            "https://localhost:8080/mcp/sse/?param=value",
            "https://localhost:8000/mcp/sse?x=1&y=2",
        ],
        ids=[
            "path_with_sse_directory",
            "path_with_sse_subdirectory",
            "path_ending_with_sse",
            "path_ending_with_sse_slash",
            "path_ending_with_sse_https",
            "path_with_sse_and_query_params",
            "path_with_sse_slash_and_query_params",
            "path_with_sse_and_ampersand_param",
        ],
    )
    def test_url_returns_sse_transport(self, url):
        """Test that URLs with /sse/ pattern return SSETransport."""
        assert isinstance(infer_transport(url), SSETransport)

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/api",
            "https://localhost:8080/mcp/",
            "http://example.com/asset/image.jpg",
            "https://localhost:8080/sservice/endpoint",
            "https://example.com/assets/file",
        ],
        ids=[
            "regular_http_url",
            "regular_https_url",
            "url_with_unrelated_path",
            "url_with_sservice_in_path",
            "url_with_assets_in_path",
        ],
    )
    def test_url_returns_streamable_http_transport(self, url):
        """Test that URLs without /sse/ pattern return StreamableHttpTransport."""
        assert isinstance(infer_transport(url), StreamableHttpTransport)

    def test_infer_remote_transport_from_config(self):
        config = {
            "mcpServers": {
                "test_server": {
                    "url": "http://localhost:8000/sse/",
                    "headers": {"Authorization": "Bearer 123"},
                },
            }
        }
        transport = infer_transport(config)
        assert isinstance(transport, MCPConfigTransport)
        assert isinstance(transport.transport, SSETransport)
        assert transport.transport.url == "http://localhost:8000/sse/"
        assert transport.transport.headers == {"Authorization": "Bearer 123"}

    def test_infer_local_transport_from_config(self):
        config = {
            "mcpServers": {
                "test_server": {
                    "command": "echo",
                    "args": ["hello"],
                },
            }
        }
        transport = infer_transport(config)
        assert isinstance(transport, MCPConfigTransport)
        assert isinstance(transport.transport, StdioTransport)
        assert transport.transport.command == "echo"
        assert transport.transport.args == ["hello"]

    def test_config_with_no_servers(self):
        """Test that an empty MCPConfig raises a ValueError."""
        config = {"mcpServers": {}}
        with pytest.raises(ValueError, match="No MCP servers defined in the config"):
            infer_transport(config)

    def test_mcpconfigtransport_with_no_servers(self):
        """Test that MCPConfigTransport raises a ValueError when initialized with an empty config."""
        config = {"mcpServers": {}}
        with pytest.raises(ValueError, match="No MCP servers defined in the config"):
            MCPConfigTransport(config=config)

    def test_infer_composite_client(self):
        config = {
            "mcpServers": {
                "local": {
                    "command": "echo",
                    "args": ["hello"],
                },
                "remote": {
                    "url": "http://localhost:8000/sse/",
                    "headers": {"Authorization": "Bearer 123"},
                },
            }
        }
        transport = infer_transport(config)
        assert isinstance(transport, MCPConfigTransport)
        # Multi-server configs create composite server at connect time
        assert len(transport.config.mcpServers) == 2

    def test_infer_fastmcp_server(self, fastmcp_server):
        """FastMCP server instances should infer to FastMCPTransport."""
        transport = infer_transport(fastmcp_server)
        assert isinstance(transport, FastMCPTransport)

    def test_infer_fastmcp_v1_server(self):
        """FastMCP 1.0 server instances should infer to FastMCPTransport."""
        from mcp.server.fastmcp import FastMCP as FastMCP1

        server = FastMCP1()
        transport = infer_transport(server)
        assert isinstance(transport, FastMCPTransport)
