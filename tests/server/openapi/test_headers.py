import pytest
import httpx
from fastapi import FastAPI, Request

from fastmcp import Client
from fastmcp.server.openapi import FastMCPOpenAPI
from fastmcp.tools.tool import ToolResult


@pytest.fixture
def header_echo_app() -> FastAPI:
    """A simple FastAPI app that echoes headers."""
    app = FastAPI(title="Header Echo App")

    @app.get("/echo_headers")
    async def echo_headers(request: Request):
        """Returns all request headers as JSON."""
        return request.headers

    return app


@pytest.mark.asyncio
async def test_mcp_tool_with_client_headers(header_echo_app: FastAPI):
    """
    Tests that headers from the FastMCP server's internal client are passed
    to the backend API when a tool is called.
    """
    # Define a random auth header value
    auth_token = "basic Zm9vOmJhcg=="  # "foo:bar"
    auth_header = {"Authorization": auth_token}

    # Create an httpx client with the default header. This client will be used
    # by the FastMCP server to communicate with the backend API.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=header_echo_app),
        base_url="http://test",
        headers=auth_header,
    ) as http_client:
        mcp_server = FastMCPOpenAPI(
            openapi_spec=header_echo_app.openapi(),
            client=http_client,
        )

        async with Client(mcp_server) as mcp_client:
            tools = await mcp_client.list_tools()
            assert len(tools) == 1
            echo_tool_name = tools[0].name
            assert "echo_headers" in echo_tool_name

            result = await mcp_client.call_tool(echo_tool_name, {})

            assert result.data is not None
            response_headers = result.data

            assert "authorization" in response_headers
            assert response_headers["authorization"] == auth_token