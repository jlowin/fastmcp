import json
from collections.abc import Generator

import pytest

from fastmcp import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport
from fastmcp.utilities.tests import run_server_in_process
from tests.client.server_for_testing import run_proxy_server, run_server


class TestClientHeaders:
    @pytest.fixture(scope="function")
    def shttp_server(self) -> Generator[str, None, None]:
        with run_server_in_process(run_server, transport="http") as url:
            yield f"{url}/mcp/"

    @pytest.fixture(scope="function")
    def sse_server(self) -> Generator[str, None, None]:
        with run_server_in_process(run_server, transport="sse") as url:
            yield f"{url}/sse/"

    @pytest.fixture(scope="function")
    def proxy_server(self, shttp_server: str) -> Generator[str, None, None]:
        with run_server_in_process(
            run_proxy_server,
            shttp_url=shttp_server,
            transport="http",
        ) as url:
            yield f"{url}/mcp/"

    async def test_client_headers_sse_resource(self, sse_server: str):
        async with Client(
            transport=SSETransport(sse_server, headers={"X-TEST": "test-123"})
        ) as client:
            result = await client.read_resource("resource://get_headers_headers_get")
            headers = json.loads(result[0].text)  # type: ignore[attr-defined]
            assert headers["x-test"] == "test-123"

    async def test_client_headers_shttp_resource(self, shttp_server: str):
        async with Client(
            transport=StreamableHttpTransport(
                shttp_server, headers={"X-TEST": "test-123"}
            )
        ) as client:
            result = await client.read_resource("resource://get_headers_headers_get")
            headers = json.loads(result[0].text)  # type: ignore[attr-defined]
            assert headers["x-test"] == "test-123"

    async def test_client_headers_sse_resource_template(self, sse_server: str):
        async with Client(
            transport=SSETransport(sse_server, headers={"X-TEST": "test-123"})
        ) as client:
            result = await client.read_resource(
                "resource://get_header_by_name_headers/x-test"
            )
            header = json.loads(result[0].text)  # type: ignore[attr-defined]
            assert header == "test-123"

    async def test_client_headers_shttp_resource_template(self, shttp_server: str):
        async with Client(
            transport=StreamableHttpTransport(
                shttp_server, headers={"X-TEST": "test-123"}
            )
        ) as client:
            result = await client.read_resource(
                "resource://get_header_by_name_headers/x-test"
            )
            header = json.loads(result[0].text)  # type: ignore[attr-defined]
            assert header == "test-123"

    async def test_client_headers_sse_tool(self, sse_server: str):
        async with Client(
            transport=SSETransport(sse_server, headers={"X-TEST": "test-123"})
        ) as client:
            result = await client.call_tool("post_headers_headers_post")
            headers: dict[str, str] = result.data
            assert headers["x-test"] == "test-123"

    async def test_client_headers_shttp_tool(self, shttp_server: str):
        async with Client(
            transport=StreamableHttpTransport(
                shttp_server, headers={"X-TEST": "test-123"}
            )
        ) as client:
            result = await client.call_tool("post_headers_headers_post")
            headers: dict[str, str] = result.data
            assert headers["x-test"] == "test-123"

    async def test_client_overrides_server_headers(self, shttp_server: str):
        async with Client(
            transport=StreamableHttpTransport(
                shttp_server, headers={"x-server-header": "test-client"}
            )
        ) as client:
            result = await client.read_resource("resource://get_headers_headers_get")
            headers = json.loads(result[0].text)  # type: ignore[attr-defined]
            assert headers["x-server-header"] == "test-client"

    async def test_client_with_excluded_header_is_ignored(self, sse_server: str):
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

    async def test_client_headers_proxy(self, proxy_server: str):
        """
        Test that client headers are passed through the proxy to the remote server.
        """
        async with Client(transport=StreamableHttpTransport(proxy_server)) as client:
            result = await client.read_resource("resource://get_headers_headers_get")
            headers = json.loads(result[0].text)  # type: ignore[attr-defined]
            assert headers["x-server-header"] == "test-abc"
