import json
import os

import pytest
from fastmcp import Client
from fastmcp.client import ClientTransport, StreamableHttpTransport
from mcp import McpError
from mcp.types import Tool

GITHUB_REMOTE_MCP_URL = "https://api.githubcopilot.com/mcp/"

HEADER_AUTHORIZATION = "Authorization"
MCP_GITHUB_PAT = os.getenv("MCP_GITHUB_PAT")


@pytest.fixture(name="streamable_http_client")
def fixture_streamable_http_client() -> Client[ClientTransport]:
    return Client(
        StreamableHttpTransport(url=GITHUB_REMOTE_MCP_URL,
                                headers={HEADER_AUTHORIZATION: f"Bearer {MCP_GITHUB_PAT}"}
                                )
    )


@pytest.mark.asyncio
async def test_connect_disconnect(streamable_http_client: Client[StreamableHttpTransport]):
    async with streamable_http_client:
        assert streamable_http_client.is_connected() is True
        await streamable_http_client._disconnect()  # pylint: disable=W0212 (protected-access)
        assert streamable_http_client.is_connected() is False


@pytest.mark.asyncio
async def test_ping(streamable_http_client: Client[StreamableHttpTransport]):
    """Test pinging the server."""
    async with streamable_http_client:
        assert streamable_http_client.is_connected() is True
        result = await streamable_http_client.ping()
        assert result is True


@pytest.mark.asyncio
async def test_list_tools(streamable_http_client: Client[StreamableHttpTransport]):
    """Test listing the MCP tools"""
    async with streamable_http_client:
        assert streamable_http_client.is_connected()
        tools = await streamable_http_client.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0  # Ensure the tools list is non-empty
        for tool in tools:
            assert isinstance(tool, Tool)
            assert len(tool.name) > 0
            assert len(tool.description) > 0
            assert isinstance(tool.inputSchema, dict)
            assert len(tool.inputSchema) > 0


@pytest.mark.asyncio
async def test_list_resources(streamable_http_client: Client[StreamableHttpTransport]):
    """Test listing the MCP resources """
    async with streamable_http_client:
        assert streamable_http_client.is_connected()
        resources = await streamable_http_client.list_resources()
        assert isinstance(resources, list)
        assert len(resources) == 0


@pytest.mark.asyncio
async def test_list_prompts(streamable_http_client: Client[StreamableHttpTransport]):
    """Test listing the MCP prompts """
    async with streamable_http_client:
        assert streamable_http_client.is_connected()
        with pytest.raises(McpError) as exc:
            await streamable_http_client.list_prompts()
        assert exc.value.args[0] == "prompts not supported"


@pytest.mark.asyncio
async def test_call_tool_ko(streamable_http_client: Client[StreamableHttpTransport]):
    """Test calling a non-existing tool"""
    async with streamable_http_client:
        assert streamable_http_client.is_connected()
        with pytest.raises(McpError, match="tool not found") as excinfo:
            await streamable_http_client.call_tool("foo")


@pytest.mark.asyncio
async def test_call_tool_list_commits(streamable_http_client: Client[StreamableHttpTransport]):
    """Test calling a list_commit tool"""
    async with streamable_http_client:
        assert streamable_http_client.is_connected()
        result = await streamable_http_client.call_tool("list_commits",
                                                        {"owner": "jlowin", "repo": "fastmcp"})
        assert isinstance(result, list)
        assert len(result) == 1
        commits = json.loads(result[0].text)
        for commit in commits:
            assert isinstance(commit, dict)
            assert "sha" in commit
            assert "commit" in commit
            assert "author" in commit["commit"]
            assert len(commit["commit"]["author"]["date"]) > 0
            assert len(commit["commit"]["author"]["name"]) > 0
            assert len(commit["commit"]["author"]["email"]) > 0
