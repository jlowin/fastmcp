"""Negotiation metadata forwarding across proxy protocol eras."""

from itertools import product
from typing import Any, Literal, TypeVar

import mcp_types
import pytest
from mcp import MCPError
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.providers.proxy import (
    ProxyClient,
    ProxyMetadataMiddleware,
    ProxyProvider,
)
from fastmcp.utilities.http import find_available_port

ResultT = TypeVar("ResultT", bound=mcp_types.Result)

UPSTREAM_INFO = mcp_types.Implementation(
    name="upstream",
    title="Upstream title",
    version="1.2.3",
    description="Upstream description",
    website_url="https://upstream.example.com",
    icons=[mcp_types.Icon(src="https://upstream.example.com/icon.png")],
)


class UpstreamMetadataMiddleware(Middleware):
    """Advertise metadata that differs from the gateway's own claims."""

    def _updates(self, result: mcp_types.Result) -> dict[str, Any]:
        meta = {
            **(result.meta or {}),
            "com.example/upstream": {"enabled": True},
            "com.example/shared": "upstream",
        }
        updates: dict[str, Any] = {
            "instructions": "upstream instructions",
            "meta": meta,
        }
        if isinstance(result, mcp_types.InitializeResult):
            updates.update(
                server_info=UPSTREAM_INFO,
                capabilities=mcp_types.ServerCapabilities(
                    experimental={"upstream": {"claimed": True}}
                ),
            )
        else:
            meta[mcp_types.SERVER_INFO_META_KEY] = UPSTREAM_INFO.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )
            updates.update(
                ttl_ms=91_000,
                cache_scope="public",
                capabilities=mcp_types.ServerCapabilities(
                    experimental={"upstream": {"claimed": True}}
                ),
            )
        return updates

    async def on_initialize(
        self,
        context: MiddlewareContext[mcp_types.InitializeRequest],
        call_next: CallNext[
            mcp_types.InitializeRequest, mcp_types.InitializeResult | None
        ],
    ) -> mcp_types.InitializeResult | None:
        result = await call_next(context)
        assert result is not None
        return result.model_copy(update=self._updates(result))

    async def on_discover(
        self,
        context: MiddlewareContext[mcp_types.DiscoverRequest],
        call_next: CallNext[mcp_types.DiscoverRequest, mcp_types.DiscoverResult],
    ) -> mcp_types.DiscoverResult:
        result = await call_next(context)
        return result.model_copy(update=self._updates(result))


class FrontendMetadataMiddleware(Middleware):
    """Set frontend values that must win over the upstream on collision."""

    def _update(self, result: ResultT) -> ResultT:
        return result.model_copy(
            update={
                "meta": {
                    **(result.meta or {}),
                    "com.example/shared": "frontend",
                    "com.example/frontend": {"enabled": True},
                },
            }
        )

    async def on_initialize(
        self,
        context: MiddlewareContext[mcp_types.InitializeRequest],
        call_next: CallNext[
            mcp_types.InitializeRequest, mcp_types.InitializeResult | None
        ],
    ) -> mcp_types.InitializeResult | None:
        result = await call_next(context)
        assert result is not None
        return self._update(result)

    async def on_discover(
        self,
        context: MiddlewareContext[mcp_types.DiscoverRequest],
        call_next: CallNext[mcp_types.DiscoverRequest, mcp_types.DiscoverResult],
    ) -> mcp_types.DiscoverResult:
        result = await call_next(context)
        return self._update(result)


def make_upstream() -> FastMCP:
    return FastMCP("unmodified-upstream", middleware=[UpstreamMetadataMiddleware()])


def make_gateway(
    upstream: FastMCP,
    *,
    backend_mode: str,
    identity: Literal["proxy", "upstream"] = "proxy",
    instructions: str | None = None,
    frontend_metadata: bool = False,
) -> FastMCP:
    provider = ProxyProvider(lambda: ProxyClient(upstream, mode=backend_mode))
    metadata = ProxyMetadataMiddleware(provider, identity=identity)
    middleware: list[Middleware] = [metadata]
    if frontend_metadata:
        middleware.append(FrontendMetadataMiddleware())
    gateway = FastMCP(
        "gateway",
        version="9.8.7",
        instructions=instructions,
        providers=[provider],
        middleware=middleware,
        cache_ttl=7,
        cache_scope="private",
    )
    gateway.provider_error_strategy = "raise"
    return gateway


@pytest.mark.parametrize(
    ("frontend_mode", "backend_mode"),
    list(product(("legacy", "auto"), repeat=2)),
)
async def test_forwards_metadata_across_all_protocol_era_combinations(
    frontend_mode: str, backend_mode: str
):
    gateway = make_gateway(make_upstream(), backend_mode=backend_mode)

    async with Client(gateway, mode=frontend_mode) as client:
        result = client.session.initialize_result or client.session.discover_result
        assert result is not None
        assert client.instructions == "upstream instructions"
        assert client.server_info is not None
        assert client.server_info.name == "gateway"
        assert result.meta is not None
        assert result.meta["com.example/upstream"] == {"enabled": True}
        stamped_info = result.meta.get(mcp_types.SERVER_INFO_META_KEY)
        assert result.capabilities.experimental is None

        if isinstance(result, mcp_types.InitializeResult):
            assert result.protocol_version not in MODERN_PROTOCOL_VERSIONS
            assert stamped_info is None
        else:
            assert stamped_info is not None
            assert stamped_info["name"] == "gateway"
            assert result.supported_versions == list(MODERN_PROTOCOL_VERSIONS)
            assert result.ttl_ms == 7_000
            assert result.cache_scope == "private"
            assert result.result_type == "complete"


@pytest.mark.parametrize("frontend_mode", ["legacy", "auto"])
@pytest.mark.parametrize("identity", ["proxy", "upstream"])
async def test_identity_policy_forwards_full_implementation(
    frontend_mode: str, identity: Literal["proxy", "upstream"]
):
    gateway = make_gateway(make_upstream(), backend_mode="auto", identity=identity)

    async with Client(gateway, mode=frontend_mode) as client:
        assert client.server_info is not None
        if identity == "proxy":
            assert client.server_info.name == "gateway"
            assert client.server_info.version == "9.8.7"
        else:
            assert client.server_info == UPSTREAM_INFO
            result = client.session.initialize_result or client.session.discover_result
            assert result is not None
            if isinstance(result, mcp_types.InitializeResult):
                assert mcp_types.SERVER_INFO_META_KEY not in (result.meta or {})
            else:
                assert result.meta is not None
                assert result.meta[mcp_types.SERVER_INFO_META_KEY]["name"] == "upstream"


@pytest.mark.parametrize("frontend_mode", ["legacy", "auto"])
async def test_frontend_values_take_precedence(frontend_mode: str):
    gateway = make_gateway(
        make_upstream(),
        backend_mode="auto",
        instructions="frontend instructions",
        frontend_metadata=True,
    )

    async with Client(gateway, mode=frontend_mode) as client:
        result = client.session.initialize_result or client.session.discover_result
        assert result is not None
        assert client.instructions == "frontend instructions"
        assert result.meta is not None
        assert result.meta["com.example/shared"] == "frontend"
        assert result.meta["com.example/frontend"] == {"enabled": True}
        assert result.meta["com.example/upstream"] == {"enabled": True}


@pytest.mark.parametrize("frontend_mode", ["legacy", "auto"])
async def test_unavailable_backend_does_not_fail_negotiation(frontend_mode: str):
    port = find_available_port()
    provider = ProxyProvider(
        lambda: ProxyClient(
            StreamableHttpTransport(f"http://127.0.0.1:{port}/mcp"), mode="auto"
        ),
        cache_ttl=0,
    )
    gateway = FastMCP(
        "available-gateway",
        providers=[provider],
        middleware=[ProxyMetadataMiddleware(provider)],
    )
    gateway.provider_error_strategy = "raise"

    async with Client(gateway, mode=frontend_mode) as client:
        assert client.server_info is not None
        assert client.server_info.name == "available-gateway"
        with pytest.raises(MCPError, match="Client failed to connect"):
            await client.list_tools()


def test_gateway_construction_does_not_create_backend_client():
    calls = 0

    def client_factory() -> ProxyClient:
        nonlocal calls
        calls += 1
        return ProxyClient(make_upstream())

    provider = ProxyProvider(client_factory)
    FastMCP(
        "lazy-gateway",
        providers=[provider],
        middleware=[ProxyMetadataMiddleware(provider)],
    )

    assert calls == 0


async def test_fastmcp_proxy_uses_public_metadata_middleware():
    proxy = create_proxy(make_upstream(), name="convenience", identity="upstream")

    assert any(
        isinstance(middleware, ProxyMetadataMiddleware)
        for middleware in proxy.middleware
    )
    async with Client(proxy, mode="auto") as client:
        assert client.instructions == "upstream instructions"
        assert client.server_info == UPSTREAM_INFO
