"""Tests for typed middleware support during modern discovery."""

import mcp_types

from fastmcp import Client, FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


async def test_on_discover_receives_and_transforms_typed_result():
    class DiscoveryMiddleware(Middleware):
        def __init__(self) -> None:
            self.request: mcp_types.DiscoverRequest | None = None
            self.result: mcp_types.DiscoverResult | None = None

        async def on_discover(
            self,
            context: MiddlewareContext[mcp_types.DiscoverRequest],
            call_next: CallNext[mcp_types.DiscoverRequest, mcp_types.DiscoverResult],
        ) -> mcp_types.DiscoverResult:
            self.request = context.message
            self.result = await call_next(context)
            return self.result.model_copy(update={"instructions": "discovered"})

    middleware = DiscoveryMiddleware()
    server = FastMCP("typed-discovery", middleware=[middleware])

    async with Client(server, mode="auto") as client:
        assert client.instructions == "discovered"

    assert isinstance(middleware.request, mcp_types.DiscoverRequest)
    assert isinstance(middleware.result, mcp_types.DiscoverResult)
