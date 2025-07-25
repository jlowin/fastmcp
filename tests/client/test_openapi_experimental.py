import json
from collections.abc import Generator

import httpx
import pytest
from fastapi import FastAPI, Request

import fastmcp
from fastmcp import Client, FastMCP
from fastmcp.client.transports import SSETransport, StreamableHttpTransport
from fastmcp.experimental.server.openapi import MCPType, RouteMap
from fastmcp.utilities.tests import run_server_in_process


def fastmcp_server_for_headers() -> FastMCP:
    fastmcp.settings.experimental.enable_new_openapi_parser = True

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
            # GET requests with path parameters go to ResourceTemplate
            RouteMap(
                methods=["GET"],
                pattern=r".*\{.*\}.*",
                mcp_type=MCPType.RESOURCE_TEMPLATE,
            ),
            # GET requests without path parameters go to Resource
            RouteMap(methods=["GET"], pattern=r".*", mcp_type=MCPType.RESOURCE),
        ],
    )

    return mcp


def run_server(host: str, port: int, **kwargs) -> None:
    fastmcp_server_for_headers().run(host=host, port=port, **kwargs)


def run_proxy_server(host: str, port: int, shttp_url: str, **kwargs) -> None:
    app = FastMCP.as_proxy(StreamableHttpTransport(shttp_url))
    app.run(host=host, port=port, **kwargs)


@pytest.fixture(scope="module")
def shttp_server() -> Generator[str, None, None]:
    with run_server_in_process(run_server, transport="http") as url:
        yield f"{url}/mcp/"


@pytest.fixture(scope="module")
def sse_server() -> Generator[str, None, None]:
    with run_server_in_process(run_server, transport="sse") as url:
        yield f"{url}/sse/"


@pytest.fixture(scope="module")
def proxy_server(shttp_server: str) -> Generator[str, None, None]:
    with run_server_in_process(
        run_proxy_server,
        shttp_url=shttp_server,
        transport="http",
    ) as url:
        yield f"{url}/mcp/"


async def test_fastapi_client_headers_streamable_http_resource(shttp_server: str):
    async with Client(transport=StreamableHttpTransport(shttp_server)) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["x-server-header"] == "test-abc"


async def test_fastapi_client_headers_sse_resource(sse_server: str):
    async with Client(transport=SSETransport(sse_server)) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["x-server-header"] == "test-abc"


async def test_fastapi_client_headers_streamable_http_tool(shttp_server: str):
    async with Client(transport=StreamableHttpTransport(shttp_server)) as client:
        result = await client.call_tool("post_headers_headers_post")
        headers: dict[str, str] = result.data
        assert headers["x-server-header"] == "test-abc"


async def test_fastapi_client_headers_sse_tool(sse_server: str):
    async with Client(transport=SSETransport(sse_server)) as client:
        result = await client.call_tool("post_headers_headers_post")
        headers: dict[str, str] = result.data
        assert headers["x-server-header"] == "test-abc"


async def test_client_headers_sse_resource(sse_server: str):
    async with Client(
        transport=SSETransport(sse_server, headers={"X-TEST": "test-123"})
    ) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["x-test"] == "test-123"


async def test_client_headers_shttp_resource(shttp_server: str):
    async with Client(
        transport=StreamableHttpTransport(shttp_server, headers={"X-TEST": "test-123"})
    ) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["x-test"] == "test-123"


async def test_client_headers_sse_resource_template(sse_server: str):
    async with Client(
        transport=SSETransport(sse_server, headers={"X-TEST": "test-123"})
    ) as client:
        result = await client.read_resource(
            "resource://get_header_by_name_headers/x-test"
        )
        header = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert header == "test-123"


async def test_client_headers_shttp_resource_template(shttp_server: str):
    async with Client(
        transport=StreamableHttpTransport(shttp_server, headers={"X-TEST": "test-123"})
    ) as client:
        result = await client.read_resource(
            "resource://get_header_by_name_headers/x-test"
        )
        header = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert header == "test-123"


async def test_client_headers_sse_tool(sse_server: str):
    async with Client(
        transport=SSETransport(sse_server, headers={"X-TEST": "test-123"})
    ) as client:
        result = await client.call_tool("post_headers_headers_post")
        headers: dict[str, str] = result.data
        assert headers["x-test"] == "test-123"


async def test_client_headers_shttp_tool(shttp_server: str):
    async with Client(
        transport=StreamableHttpTransport(shttp_server, headers={"X-TEST": "test-123"})
    ) as client:
        result = await client.call_tool("post_headers_headers_post")
        headers: dict[str, str] = result.data
        assert headers["x-test"] == "test-123"


async def test_client_overrides_server_headers(shttp_server: str):
    async with Client(
        transport=StreamableHttpTransport(
            shttp_server, headers={"x-server-header": "test-client"}
        )
    ) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["x-server-header"] == "test-client"


async def test_client_with_excluded_header_is_ignored(sse_server: str):
    async with Client(
        transport=SSETransport(
            sse_server,
            headers={
                "x-server-header": "test-client",
                "host": "1.2.3.4",
                "not-host": "1.2.3.4",
            },
        )
    ) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["not-host"] == "1.2.3.4"
        assert headers["host"] == "fastapi"


async def test_client_headers_proxy(proxy_server: str):
    """
    Test that client headers are passed through the proxy to the remove server.
    """
    async with Client(transport=StreamableHttpTransport(proxy_server)) as client:
        result = await client.read_resource("resource://get_headers_headers_get")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["x-server-header"] == "test-abc"


def openapi_server_for_headers() -> FastMCP:
    """Create OpenAPI server that uses httpbin for testing headers - reproduces issue #1253"""

    fastmcp.settings.experimental.enable_new_openapi_parser = True

    # Create OpenAPI spec that uses httpbin endpoints
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Headers Test API", "version": "1.0.0"},
        "servers": [{"url": "https://httpbin.org"}],
        "paths": {
            "/headers": {
                "get": {
                    "operationId": "get_headers",
                    "responses": {"200": {"description": "Get headers"}},
                }
            },
            "/post": {
                "post": {
                    "operationId": "post_data",
                    "responses": {"200": {"description": "Post data with headers"}},
                }
            },
        },
    }

    # Create client with server headers (exactly like FastAPI test)
    http_client = httpx.AsyncClient(
        base_url="https://httpbin.org", headers={"x-server-header": "test-abc"}
    )

    mcp = FastMCP.from_openapi(
        openapi_spec,
        client=http_client,
        route_maps=[
            RouteMap(methods=["GET"], pattern=r".*", mcp_type=MCPType.RESOURCE),
            RouteMap(methods=["POST"], pattern=r".*", mcp_type=MCPType.TOOL),
        ],
    )

    return mcp


def run_openapi_server(host: str, port: int, **kwargs) -> None:
    openapi_server_for_headers().run(host=host, port=port, **kwargs)


@pytest.fixture(scope="module")
def openapi_shttp_server() -> Generator[str, None, None]:
    with run_server_in_process(run_openapi_server, transport="http") as url:
        yield f"{url}/mcp/"


async def test_openapi_server_headers_streamable_http_resource(
    openapi_shttp_server: str,
):
    """Test OpenAPI server preserves headers in HTTP resource - reproduces issue #1253"""
    async with Client(
        transport=StreamableHttpTransport(openapi_shttp_server)
    ) as client:
        result = await client.read_resource("resource://get_headers")
        headers = json.loads(result[0].text)  # type: ignore[attr-defined]
        assert headers["headers"]["X-Server-Header"] == "test-abc"


async def test_openapi_server_headers_streamable_http_tool(openapi_shttp_server: str):
    """Test OpenAPI server preserves headers in HTTP tool - reproduces issue #1253"""
    async with Client(
        transport=StreamableHttpTransport(openapi_shttp_server)
    ) as client:
        result = await client.call_tool("post_data")
        headers = result.data["headers"]

        # Headers from httpx client are properly preserved in both parsers
        assert headers["X-Server-Header"] == "test-abc"
