"""Deprecation bridge for legacy-httpx OpenAPI clients."""

import pytest

from fastmcp import Client, FastMCP, FastMCPDeprecationWarning

httpx = pytest.importorskip("httpx", reason="legacy httpx not installed")

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Legacy Client API", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/items": {
            "get": {
                "operationId": "list_items",
                "responses": {
                    "200": {
                        "description": "Items",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


async def test_legacy_client_warns_and_remains_usable() -> None:
    def handler(request: "httpx.Request") -> "httpx.Response":
        return httpx.Response(200, json={"items": ["a", "b"]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.example.com",
    ) as client:
        with pytest.warns(
            FastMCPDeprecationWarning,
            match="httpx.AsyncClient.*deprecated",
        ):
            server = FastMCP.from_openapi(SPEC, client=client)

        async with Client(server) as mcp_client:
            result = await mcp_client.call_tool("list_items", {})

    assert result.structured_content == {"items": ["a", "b"]}
