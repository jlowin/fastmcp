"""Tests for MCPBundles Connect Auth provider."""

from __future__ import annotations

import pytest

from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.mcpbundles import (
    McpbundlesConnectProvider,
    PublicConfig,
)

SAMPLE_PUBLIC_CONFIG: PublicConfig = {
    "issuer": "https://api.example.com/connect-auth/tenants/demo/",
    "scopes_supported": ["read", "write"],
    "origin_resource": "https://mcp.example.com/mcp",
    "bundle_proxy_resource": "https://mcp.mcpbundles.com/bundle/demo",
}

SAMPLE_OAUTH_METADATA = {
    "issuer": "https://api.example.com/connect-auth/tenants/demo",
    "authorization_endpoint": "https://www.example.com/connect-auth/demo/authorize",
    "token_endpoint": "https://api.example.com/connect-auth/tenants/demo/o/token",
    "registration_endpoint": "https://api.example.com/connect-auth/tenants/demo/o/register",
}


def _provider(
    *,
    listing_slug: str = "demo",
    base_url: str = "https://mcp.example.com",
    public_config: PublicConfig = SAMPLE_PUBLIC_CONFIG,
) -> McpbundlesConnectProvider:
    return McpbundlesConnectProvider(
        listing_slug=listing_slug,
        base_url=base_url,
        public_config=public_config,
    )


class TestMcpbundlesConnectProvider:
    def test_init_requires_listing_slug(self) -> None:
        with pytest.raises(ValueError, match="listing_slug is required"):
            McpbundlesConnectProvider(
                listing_slug="",
                base_url="https://mcp.example.com",
                public_config=SAMPLE_PUBLIC_CONFIG,
            )

    def test_provider_configures_jwt_verifier(self) -> None:
        provider = _provider()

        assert isinstance(provider.token_verifier, JWTVerifier)
        assert provider.token_verifier.issuer == SAMPLE_PUBLIC_CONFIG["issuer"]
        assert provider.token_verifier.algorithm == "ES256"
        assert provider.token_verifier.audience == [
            SAMPLE_PUBLIC_CONFIG["origin_resource"],
            SAMPLE_PUBLIC_CONFIG["bundle_proxy_resource"],
        ]
        jwks_uri = provider.token_verifier.jwks_uri
        assert jwks_uri is not None
        assert jwks_uri.endswith("/connect-auth/tenants/demo/.well-known/jwks.json")

    def test_provider_authorization_servers(self) -> None:
        provider = _provider()

        assert len(provider.authorization_servers) == 1
        assert str(provider.authorization_servers[0]).endswith(
            "/connect-auth/tenants/demo"
        )

    @pytest.mark.asyncio
    async def test_metadata_route_forwards_tenant_response(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        provider = _provider()
        routes = provider.get_routes(mcp_path="/mcp")
        metadata_route = next(
            route
            for route in routes
            if getattr(route, "path", None) == "/.well-known/oauth-authorization-server"
        )

        class DummyResponse:
            status_code = 200

            def json(self):
                return SAMPLE_OAUTH_METADATA

            def raise_for_status(self):
                return None

        class DummyAsyncClient:
            last_url: str | None = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                DummyAsyncClient.last_url = url
                return DummyResponse()

        monkeypatch.setattr(
            "fastmcp.server.auth.providers.mcpbundles.httpx2.AsyncClient",
            DummyAsyncClient,
        )

        response = await metadata_route.endpoint(None)  # type: ignore[arg-type]

        assert response.status_code == 200
        assert DummyAsyncClient.last_url is not None
        assert DummyAsyncClient.last_url.endswith(
            "/connect-auth/tenants/demo/.well-known/oauth-authorization-server"
        )
