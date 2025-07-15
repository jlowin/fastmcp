import httpx
import pytest
from fastapi import FastAPI

from fastmcp import Client
from fastmcp.server.openapi import FastMCPOpenAPI


@pytest.mark.asyncio
async def test_mcp_tool_with_client_headers(fastapi_app: FastAPI):
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
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="http://test",
        headers=auth_header,
    ) as http_client:
        mcp_server = FastMCPOpenAPI(
            openapi_spec=fastapi_app.openapi(),
            client=http_client,
        )

        async with Client(mcp_server) as mcp_client:
            tools = await mcp_client.list_tools()
            echo_tool = next(
                (t for t in tools if "echo_headers" in t.name),
                None,
            )
            assert echo_tool is not None, "echo_headers tool not found"

            result = await mcp_client.call_tool(echo_tool.name, {})

            assert result.data is not None
            response_headers = result.data

            assert "authorization" in response_headers
            assert response_headers["authorization"] == auth_token
