"""
This module contains server setup functions for use in client tests.

It is isolated in its own file to prevent issues with multiprocessing on Windows,
where test files can be re-imported in child processes.
"""

from fastapi import FastAPI, Request

from fastmcp import FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.openapi import MCPType, RouteMap


def fastmcp_server_for_headers() -> FastMCP:
    """Creates a FastMCP server with endpoints for testing header propagation."""
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
        route_maps=[
            RouteMap(
                methods=["GET"],
                pattern=r".*\{.*\}.*",
                mcp_type=MCPType.RESOURCE_TEMPLATE,
            ),
            RouteMap(methods=["GET"], pattern=r".*", mcp_type=MCPType.RESOURCE),
        ],
    )

    return mcp


def run_server(host: str, port: int, **kwargs) -> None:
    """Runs the header-testing MCP server."""
    fastmcp_server_for_headers().run(host=host, port=port, **kwargs)


def run_proxy_server(host: str, port: int, shttp_url: str, **kwargs) -> None:
    """Runs an MCP proxy server."""
    app = FastMCP.as_proxy(StreamableHttpTransport(shttp_url))
    app.run(host=host, port=port, **kwargs)
