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


if __name__ == "__main__":
    import sys

    # This block allows the file to be run as a script to start a specific server,
    # which is necessary for the multiprocessing logic in `run_server_in_process`
    # to work correctly on Windows.
    server_type = sys.argv[1]
    host = sys.argv[2]
    port = int(sys.argv[3])
    transport = sys.argv[4]

    if server_type == "run_server":
        run_server(host=host, port=port, transport=transport)
    elif server_type == "run_proxy_server":
        shttp_url = sys.argv[5]
        run_proxy_server(host=host, port=port, shttp_url=shttp_url, transport=transport)
