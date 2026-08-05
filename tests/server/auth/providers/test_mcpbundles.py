"""Tests for MCPBundles Connect Auth provider."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from joserfc import jwk as jose_jwk
from joserfc import jwt

from fastmcp.server.auth.providers.mcpbundles import (
    McpbundlesConnectProvider,
    McpbundlesJWTVerifier,
    PublicConfig,
    connect_auth_callback_identity,
)
from fastmcp.server.auth import AccessToken

GOLDEN_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "connect_auth" / "golden_access_token.json"
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


def _sign_es256_token(
    *,
    private_key: jose_jwk.ECKey,
    kid: str,
    issuer: str,
    audience: str | list[str],
    subject: str = "user-123",
    client_id: str | None = None,
    organization_id: str | None = None,
    scope: str | None = None,
) -> str:
    header = {"alg": "ES256", "typ": "JWT", "kid": kid}
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    if client_id is not None:
        payload["client_id"] = client_id
    if organization_id is not None:
        payload["organization_id"] = organization_id
    if scope is not None:
        payload["scope"] = scope
    return jwt.encode(header, payload, private_key, algorithms=["ES256"])


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

        assert isinstance(provider.token_verifier, McpbundlesJWTVerifier)
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

    @pytest.mark.asyncio
    async def test_es256_token_verification(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        signing_key = jose_jwk.ECKey.generate_key("P-256")
        jwks_entry = signing_key.as_dict(private=False)
        jwks_entry["kid"] = "tenant-key-1"
        jwks_entry["alg"] = "ES256"
        jwks_entry["use"] = "sig"

        provider = _provider()
        verifier = provider.token_verifier
        assert isinstance(verifier, McpbundlesJWTVerifier)

        async def mock_fetch_jwks(_self: McpbundlesJWTVerifier) -> dict[str, Any]:
            return {"keys": [jwks_entry]}

        monkeypatch.setattr(McpbundlesJWTVerifier, "_fetch_jwks", mock_fetch_jwks)

        token = _sign_es256_token(
            private_key=signing_key,
            kid="tenant-key-1",
            issuer=SAMPLE_PUBLIC_CONFIG["issuer"],
            audience=SAMPLE_PUBLIC_CONFIG["origin_resource"],
            subject="user-123",
            client_id="mcp-client-xyz",
            organization_id="org-456",
            scope="read write",
        )

        access_token = await verifier.verify_token(token)

        assert access_token is not None
        assert access_token.subject == "user-123"
        assert access_token.client_id == "mcp-client-xyz"
        assert access_token.client_id != access_token.subject
        assert access_token.scopes == ["read", "write"]
        assert access_token.claims.get("organization_id") == "org-456"

    @pytest.mark.asyncio
    async def test_rejects_token_missing_client_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        signing_key = jose_jwk.ECKey.generate_key("P-256")
        jwks_entry = signing_key.as_dict(private=False)
        jwks_entry["kid"] = "tenant-key-1"
        jwks_entry["alg"] = "ES256"

        verifier = McpbundlesJWTVerifier(
            jwks_uri="https://api.example.com/connect-auth/tenants/demo/.well-known/jwks.json",
            issuer=SAMPLE_PUBLIC_CONFIG["issuer"],
            algorithm="ES256",
            audience=SAMPLE_PUBLIC_CONFIG["origin_resource"],
        )

        async def mock_fetch_jwks(_self: McpbundlesJWTVerifier) -> dict[str, Any]:
            return {"keys": [jwks_entry]}

        monkeypatch.setattr(McpbundlesJWTVerifier, "_fetch_jwks", mock_fetch_jwks)

        token = _sign_es256_token(
            private_key=signing_key,
            kid="tenant-key-1",
            issuer=SAMPLE_PUBLIC_CONFIG["issuer"],
            audience=SAMPLE_PUBLIC_CONFIG["origin_resource"],
            subject="user-only-subject",
        )

        access_token = await verifier.verify_token(token)

        assert access_token is None

    @pytest.mark.asyncio
    async def test_golden_fixture_maps_identity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fixture = json.loads(GOLDEN_FIXTURE_PATH.read_text())
        jwks_entry = fixture["jwks"]["keys"][0]

        verifier = McpbundlesJWTVerifier(
            jwks_uri="https://api.example.com/connect-auth/tenants/golden-demo/.well-known/jwks.json",
            issuer=fixture["issuer"],
            algorithm="ES256",
            audience=[
                fixture["origin_resource"],
                fixture["bundle_proxy_resource"],
            ],
        )

        async def mock_fetch_jwks(_self: McpbundlesJWTVerifier) -> dict[str, Any]:
            return {"keys": [jwks_entry]}

        monkeypatch.setattr(McpbundlesJWTVerifier, "_fetch_jwks", mock_fetch_jwks)

        access_token = await verifier.verify_token(fixture["token"])

        assert access_token is not None
        expected = fixture["expected"]
        assert access_token.subject == expected["user_id"]
        assert access_token.client_id == expected["client_id"]
        assert access_token.client_id != access_token.subject
        assert access_token.scopes == expected["scopes"]
        assert access_token.claims.get("organization_id") == expected["organization_id"]
        assert access_token.claims.get("email") == expected["email"]
        assert access_token.claims.get("roles") == expected["roles"]

    def test_connect_auth_callback_identity_matches_golden_fixture(self) -> None:
        fixture = json.loads(GOLDEN_FIXTURE_PATH.read_text())
        expected = fixture["expected"]
        access_token = AccessToken(
            token=fixture["token"],
            client_id=expected["client_id"],
            scopes=expected["scopes"],
            expires_at=fixture["claims"]["exp"],
            subject=expected["user_id"],
            claims=fixture["claims"],
        )

        identity = connect_auth_callback_identity(access_token)

        assert identity == {
            "user": {
                "id": expected["user_id"],
                "organizationId": expected["organization_id"],
                "email": expected["email"],
                "roles": expected["roles"],
            },
            "auth": {
                "clientId": expected["client_id"],
                "scopes": expected["scopes"],
                "expiresAt": fixture["claims"]["exp"],
                "resource": fixture["origin_resource"],
            },
        }

    @pytest.mark.asyncio
    async def test_jwks_verifier_retries_once_on_unknown_kid(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        old_signing_key = jose_jwk.ECKey.generate_key("P-256")
        new_signing_key = jose_jwk.ECKey.generate_key("P-256")
        old_jwk = old_signing_key.as_dict(private=False)
        old_jwk["kid"] = "old-kid"
        old_jwk["alg"] = "ES256"
        new_jwk = new_signing_key.as_dict(private=False)
        new_jwk["kid"] = "new-kid"
        new_jwk["alg"] = "ES256"

        fetch_count = 0

        async def mock_fetch_jwks(_self: McpbundlesJWTVerifier) -> dict[str, Any]:
            nonlocal fetch_count
            fetch_count += 1
            if fetch_count == 1:
                return {"keys": [old_jwk]}
            return {"keys": [new_jwk]}

        verifier = McpbundlesJWTVerifier(
            jwks_uri="https://api.example.com/connect-auth/tenants/demo/.well-known/jwks.json",
            issuer=SAMPLE_PUBLIC_CONFIG["issuer"],
            algorithm="ES256",
            audience=SAMPLE_PUBLIC_CONFIG["origin_resource"],
        )
        monkeypatch.setattr(McpbundlesJWTVerifier, "_fetch_jwks", mock_fetch_jwks)

        await verifier._get_jwks_key("old-kid")
        assert fetch_count == 1

        token = _sign_es256_token(
            private_key=new_signing_key,
            kid="new-kid",
            issuer=SAMPLE_PUBLIC_CONFIG["issuer"],
            audience=SAMPLE_PUBLIC_CONFIG["origin_resource"],
            client_id="client-after-rotation",
        )

        access_token = await verifier.verify_token(token)

        assert access_token is not None
        assert access_token.client_id == "client-after-rotation"
        assert fetch_count == 2
