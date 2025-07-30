"""Tests for OAuth proxy provider."""

from typing import cast

import pytest
from mcp.server.auth.provider import AccessToken, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.routing import BaseRoute, Route

from fastmcp.server.auth.auth import TokenVerifier
from fastmcp.server.auth.providers.proxy import OAuthProxy


class MockTokenVerifier(TokenVerifier):
    """Simple mock token verifier for testing."""

    def __init__(
        self, should_validate: bool = True, required_scopes: list[str] | None = None
    ):
        super().__init__(required_scopes=required_scopes)
        self.should_validate = should_validate
        self.verified_tokens: list[str] = []

    async def verify_token(self, token: str) -> AccessToken | None:
        self.verified_tokens.append(token)
        if not self.should_validate:
            return None
        return AccessToken(
            token=token,
            client_id="test-client",
            scopes=self.required_scopes or [],
            expires_at=None,
        )


class TestOAuthProxyInit:
    """Test OAuth proxy initialization."""

    def test_creates_proxy_with_required_token_verifier(self):
        """Test that proxy requires token_verifier parameter."""
        token_verifier = MockTokenVerifier()

        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        assert (
            proxy._upstream_authorization_endpoint
            == "https://auth.example.com/authorize"
        )
        assert proxy._upstream_token_endpoint == "https://auth.example.com/token"
        assert proxy._upstream_client_id == "upstream-client"
        assert proxy._token_validator is token_verifier

    def test_inherits_required_scopes_from_token_verifier(self):
        """Test that proxy uses token verifier's required scopes."""
        token_verifier = MockTokenVerifier(required_scopes=["read", "write"])

        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        assert proxy.required_scopes == ["read", "write"]

    def test_sets_up_revocation_when_endpoint_provided(self):
        """Test that revocation is configured when upstream endpoint provided."""
        token_verifier = MockTokenVerifier()

        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            upstream_revocation_endpoint="https://auth.example.com/revoke",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        assert proxy.revocation_options is not None
        assert proxy.revocation_options.enabled is True


class TestOAuthProxyClientRegistration:
    """Test client registration functionality."""

    @pytest.fixture
    def proxy(self):
        """Create a test proxy instance."""
        token_verifier = MockTokenVerifier()
        return OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

    async def test_register_client_returns_upstream_credentials(self, proxy):
        """Test that client registration always returns upstream credentials."""
        client_info = OAuthClientInformationFull(
            client_id="requested-client-id",
            client_secret="requested-secret",
            redirect_uris=[AnyUrl("https://app.example.com/callback")],
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
        )

        registered_client = await proxy.register_client(client_info)

        # Should use upstream credentials, not requested ones
        assert registered_client.client_id == "upstream-client"
        assert registered_client.client_secret == "upstream-secret"
        # But preserve other metadata
        assert registered_client.redirect_uris == client_info.redirect_uris
        assert registered_client.grant_types == ["authorization_code"]

    async def test_get_client_returns_registered_client(self, proxy):
        """Test that get_client returns previously registered clients."""
        client_info = OAuthClientInformationFull(
            client_id="any-id",
            redirect_uris=[AnyUrl("https://app.example.com/callback")],
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
        )

        # Register client first
        await proxy.register_client(client_info)

        # Should return the registered client with upstream credentials
        retrieved_client = await proxy.get_client("upstream-client")
        assert retrieved_client is not None
        assert retrieved_client.client_id == "upstream-client"

    async def test_get_client_creates_temporary_client_for_unknown_id(self, proxy):
        """Test that get_client creates temporary client for unknown IDs."""
        client = await proxy.get_client("unknown-client-id")

        assert client is not None
        assert client.client_id == "unknown-client-id"
        assert client.redirect_uris == [proxy.issuer_url]


class TestOAuthProxyAuthorizationFlow:
    """Test authorization flow functionality."""

    @pytest.fixture
    def proxy(self):
        """Create a test proxy instance."""
        token_verifier = MockTokenVerifier()
        return OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

    async def test_authorize_builds_upstream_url(self, proxy):
        """Test that authorize builds correct upstream authorization URL."""
        client = OAuthClientInformationFull(
            client_id="test-client",
            redirect_uris=[AnyUrl("https://app.example.com/callback")],
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
        )

        params = AuthorizationParams(
            redirect_uri=AnyUrl("https://app.example.com/callback"),
            redirect_uri_provided_explicitly=True,
            state="test-state",
            scopes=["read", "write"],
            code_challenge="test-challenge",
        )

        upstream_url = await proxy.authorize(client, params)

        # Should redirect to upstream with correct parameters
        assert upstream_url.startswith("https://auth.example.com/authorize?")
        assert "client_id=upstream-client" in upstream_url
        assert "redirect_uri=" in upstream_url and "app.example.com" in upstream_url
        assert "state=test-state" in upstream_url
        assert "scope=read+write" in upstream_url
        assert "code_challenge=test-challenge" in upstream_url
        assert "code_challenge_method=S256" in upstream_url

    async def test_load_authorization_code_creates_minimal_code(self, proxy):
        """Test that load_authorization_code creates a minimal authorization code object."""
        client = OAuthClientInformationFull(
            client_id="test-client",
            redirect_uris=[AnyUrl("https://app.example.com/callback")],
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
        )

        auth_code = await proxy.load_authorization_code(client, "test-auth-code")

        assert auth_code is not None
        assert auth_code.code == "test-auth-code"
        assert auth_code.client_id == "test-client"


class TestOAuthProxyTokenValidation:
    """Test token validation delegation."""

    async def test_load_access_token_delegates_to_verifier(self):
        """Test that token validation is delegated to the token verifier."""
        token_verifier = MockTokenVerifier(should_validate=True)
        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        # Call should be delegated to token verifier
        result = await proxy.load_access_token("test-token")

        # Verify delegation happened
        assert len(token_verifier.verified_tokens) == 1
        assert token_verifier.verified_tokens[0] == "test-token"
        assert result is not None
        assert result.token == "test-token"

    async def test_load_access_token_returns_none_for_invalid_token(self):
        """Test that invalid tokens return None."""
        token_verifier = MockTokenVerifier(should_validate=False)
        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        # Should return None for invalid token
        result = await proxy.load_access_token("invalid-token")
        assert result is None


class TestOAuthProxyRouteCustomization:
    """Test route customization functionality."""

    def test_customize_auth_routes_replaces_token_endpoint(self):
        """Test that route customization replaces the token endpoint."""
        token_verifier = MockTokenVerifier()
        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        # Create mock routes including a token route
        original_routes: list[BaseRoute] = [
            Route("/authorize", endpoint=lambda: None, methods=["GET"]),
            Route("/token", endpoint=lambda: None, methods=["POST"]),
            Route("/register", endpoint=lambda: None, methods=["POST"]),
        ]

        customized_routes = proxy.customize_auth_routes(original_routes)

        # Should have same number of routes
        assert len(customized_routes) == len(original_routes)

        # Token route should be replaced with proxy handler
        token_routes = [
            cast(Route, r)
            for r in customized_routes
            if hasattr(r, "path") and getattr(r, "path") == "/token"
        ]
        assert len(token_routes) == 1
        assert token_routes[0].endpoint == proxy._handle_proxy_token_request

        # Other routes should be unchanged
        auth_routes = [
            cast(Route, r)
            for r in customized_routes
            if hasattr(r, "path") and getattr(r, "path") == "/authorize"
        ]
        register_routes = [
            cast(Route, r)
            for r in customized_routes
            if hasattr(r, "path") and getattr(r, "path") == "/register"
        ]
        assert len(auth_routes) == 1
        assert len(register_routes) == 1
        assert auth_routes[0].endpoint == cast(Route, original_routes[0]).endpoint
        assert register_routes[0].endpoint == cast(Route, original_routes[2]).endpoint

    def test_customize_auth_routes_preserves_non_token_routes(self):
        """Test that non-token routes are preserved unchanged."""
        token_verifier = MockTokenVerifier()
        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        # Create routes without token endpoint
        original_routes: list[BaseRoute] = [
            Route("/authorize", endpoint=lambda: None, methods=["GET"]),
            Route("/register", endpoint=lambda: None, methods=["POST"]),
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=lambda: None,
                methods=["GET"],
            ),
        ]

        customized_routes = proxy.customize_auth_routes(original_routes)

        # Should be identical since no token route to replace
        assert len(customized_routes) == len(original_routes)
        for original, customized in zip(original_routes, customized_routes):
            original_route = cast(Route, original)
            customized_route = cast(Route, customized)
            assert original_route.path == customized_route.path
            assert original_route.endpoint == customized_route.endpoint
            assert original_route.methods == customized_route.methods


class TestOAuthProxyIntegration:
    """Integration test with FastMCP server."""

    def test_proxy_can_be_used_with_fastmcp_server(self):
        """Test that OAuthProxy can be used to create a FastMCP server."""
        from fastmcp import FastMCP

        token_verifier = MockTokenVerifier(required_scopes=["api:read"])
        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://auth.example.com/authorize",
            upstream_token_endpoint="https://auth.example.com/token",
            upstream_client_id="upstream-client",
            upstream_client_secret="upstream-secret",
            token_verifier=token_verifier,
            issuer_url="https://my-server.com",
        )

        # Should be able to create FastMCP server with proxy
        mcp = FastMCP("Test Server", auth=proxy)

        # Server should inherit auth settings from proxy
        assert mcp.auth is proxy

        # Should be able to create HTTP app
        app = mcp.http_app()
        assert app is not None

        # App should have auth routes from proxy (including custom token endpoint)
        routes = [route for route in app.routes if hasattr(route, "path")]
        route_paths = [route.path for route in routes]  # type: ignore[attr-defined]

        # Should have OAuth endpoints
        assert "/token" in route_paths
        assert "/authorize" in route_paths
        assert "/register" in route_paths
