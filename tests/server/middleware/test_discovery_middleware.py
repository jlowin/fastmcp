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


async def test_on_discover_forwards_modified_params():
    modified = False
    server = FastMCP("modified-discovery")
    default_handler = server._mcp_server._handle_discover

    async def capture_params(ctx, params):
        nonlocal modified
        assert params is not None
        assert params.meta is not None
        modified = params.meta["com.example/modified"] is True
        return await default_handler(ctx, params)

    server._mcp_server.add_request_handler(
        "server/discover", mcp_types.RequestParams, capture_params
    )

    class ModifyParams(Middleware):
        async def on_discover(self, context, call_next):
            assert context.message.params is not None
            assert context.message.params.meta is not None
            context.message.params = mcp_types.RequestParams(
                meta={
                    **context.message.params.meta,
                    "com.example/modified": True,
                }
            )
            return await call_next(context)

    server.add_middleware(ModifyParams())

    async with Client(server, mode="auto"):
        pass

    assert modified
