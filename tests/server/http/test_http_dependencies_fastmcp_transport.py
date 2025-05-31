import json

from mcp.types import TextContent, TextResourceContents

from fastmcp.client import Client
from fastmcp.client.transports import (
    FastMCPTransport,
)
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.server import FastMCP

"""
Analogue of test_http_dependencies.py, but using FastMCPTransport instead of
StreamableHttpTransport or SSETransport. There are issues in CI when comining
ASGITransport and actual servers.
"""


def fastmcp_server():
    server = FastMCP()

    # Add a tool
    @server.tool()
    def get_headers_tool() -> dict[str, str]:
        """Get the HTTP headers from the request."""
        request = get_http_request()

        return dict(request.headers)

    @server.resource(uri="request://headers")
    async def get_headers_resource() -> dict[str, str]:
        request = get_http_request()

        return dict(request.headers)

    # Add a prompt
    @server.prompt()
    def get_headers_prompt() -> str:
        """Get the HTTP headers from the request."""
        request = get_http_request()

        return json.dumps(dict(request.headers))

    return server


async def test_http_headers_resource_fastmcp():
    async with Client(
        transport=FastMCPTransport(
            fastmcp_server(),
            transport="streamable-http",
            transport_kwargs={"headers": {"X-DEMO-HEADER": "ABC"}},
        )
    ) as client:
        raw_result = await client.read_resource("request://headers")
        assert isinstance(raw_result[0], TextResourceContents)
        json_result = json.loads(raw_result[0].text)
        assert "x-demo-header" in json_result
        assert json_result["x-demo-header"] == "ABC"


async def test_http_headers_tool_fastmcp():
    async with Client(
        transport=FastMCPTransport(
            fastmcp_server(),
            transport="streamable-http",
            transport_kwargs={"headers": {"X-DEMO-HEADER": "ABC"}},
        )
    ) as client:
        result = await client.call_tool("get_headers_tool")
        assert isinstance(result[0], TextContent)
        json_result = json.loads(result[0].text)
        assert "x-demo-header" in json_result
        assert json_result["x-demo-header"] == "ABC"


async def test_http_headers_prompt_fastmcp():
    async with Client(
        transport=FastMCPTransport(
            fastmcp_server(),
            transport="streamable-http",
            transport_kwargs={"headers": {"X-DEMO-HEADER": "ABC"}},
        )
    ) as client:
        result = await client.get_prompt("get_headers_prompt")
        assert isinstance(result.messages[0].content, TextContent)
        json_result = json.loads(result.messages[0].content.text)
        assert "x-demo-header" in json_result
        assert json_result["x-demo-header"] == "ABC"
