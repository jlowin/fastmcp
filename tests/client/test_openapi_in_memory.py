import json

from fastapi import FastAPI, Request
from mcp.types import TextContent, TextResourceContents

from fastmcp import Client, FastMCP
from fastmcp.client.transports import (
    FastMCPTransport,
)


def fastmcp_server_for_headers() -> FastMCP:
    app = FastAPI()

    @app.get("/headers")
    def get_headers(request: Request):
        return request.headers

    @app.get("/headers/{header_name}")
    def get_header_by_name(header_name: str, request: Request):
        return request.headers[header_name]

    @app.post("/headers")
    def post_headers(request: Request):
        return request.headers

    mcp = FastMCP.from_fastapi(
        app,
        httpx_client_kwargs={"headers": {"x-server-header": "test-abc"}},
    )

    return mcp


class TestClientHeaders:
    async def test_client_headers_fastmcp_resource(self):
        async with Client(
            transport=FastMCPTransport(
                fastmcp_server_for_headers(),
                transport="streamable-http",
                transport_kwargs={"headers": {"X-TEST": "test-123"}},
            )
        ) as client:
            result = await client.read_resource("resource://get_headers_headers_get")
            assert isinstance(result[0], TextResourceContents)
            headers = json.loads(result[0].text)
            assert headers["x-test"] == "test-123"

    async def test_client_headers_fastmcp_resource_template(self):
        async with Client(
            transport=FastMCPTransport(
                fastmcp_server_for_headers(),
                transport="streamable-http",
                transport_kwargs={"headers": {"X-TEST": "test-123"}},
            )
        ) as client:
            result = await client.read_resource(
                "resource://get_header_by_name_headers/x-test"
            )
            assert isinstance(result[0], TextResourceContents)
            header = json.loads(result[0].text)
            assert header == "test-123"

    async def test_client_headers_fastmcp_tool(self):
        async with Client(
            transport=FastMCPTransport(
                fastmcp_server_for_headers(),
                transport="streamable-http",
                transport_kwargs={"headers": {"X-TEST": "test-123"}},
            )
        ) as client:
            result = await client.call_tool("post_headers_headers_post")
            assert isinstance(result[0], TextContent)
            headers = json.loads(result[0].text)
            assert headers["x-test"] == "test-123"
