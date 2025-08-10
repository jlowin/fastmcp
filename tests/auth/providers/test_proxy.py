"""Tests for OAuth Proxy Provider."""

import pytest
from pydantic import AnyHttpUrl

from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.proxy import OAuthProxy


class TestOAuthProxy:
    """Test suite for OAuthProxy provider."""

    def test_proxy_initialization(self):
        """Test that OAuthProxy initializes correctly."""
        # Create a JWT verifier for token validation
        jwt_verifier = JWTVerifier(
            jwks_uri="https://example.com/.well-known/jwks.json",
            issuer="https://example.com",
            audience="test-audience",
        )

        # Initialize the proxy
        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://upstream.com/authorize",
            upstream_token_endpoint="https://upstream.com/token",
            upstream_client_id="upstream-client-id",
            upstream_client_secret="upstream-client-secret",
            token_verifier=jwt_verifier,
            base_url="https://fastmcp.com",
        )

        # Verify initialization
        assert proxy._upstream_authorization_endpoint == "https://upstream.com/authorize"
        assert proxy._upstream_token_endpoint == "https://upstream.com/token"
        assert proxy._upstream_client_id == "upstream-client-id"
        assert proxy._upstream_client_secret.get_secret_value() == "upstream-client-secret"
        assert proxy.base_url == AnyHttpUrl("https://fastmcp.com")
        assert proxy._token_validator == jwt_verifier

    def test_proxy_with_revocation_endpoint(self):
        """Test proxy initialization with revocation endpoint."""
        jwt_verifier = JWTVerifier(
            jwks_uri="https://example.com/.well-known/jwks.json",
            issuer="https://example.com",
            audience="test-audience",
        )

        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://upstream.com/authorize",
            upstream_token_endpoint="https://upstream.com/token",
            upstream_client_id="upstream-client-id",
            upstream_client_secret="upstream-client-secret",
            upstream_revocation_endpoint="https://upstream.com/revoke",
            token_verifier=jwt_verifier,
            base_url="https://fastmcp.com",
        )

        assert proxy._upstream_revocation_endpoint == "https://upstream.com/revoke"
        assert proxy.revocation_options is not None
        assert proxy.revocation_options.enabled is True

    def test_proxy_enables_dcr_by_default(self):
        """Test that proxy enables DCR by default."""
        jwt_verifier = JWTVerifier(
            jwks_uri="https://example.com/.well-known/jwks.json",
            issuer="https://example.com",
            audience="test-audience",
        )

        proxy = OAuthProxy(
            upstream_authorization_endpoint="https://upstream.com/authorize",
            upstream_token_endpoint="https://upstream.com/token",
            upstream_client_id="upstream-client-id",
            upstream_client_secret="upstream-client-secret",
            token_verifier=jwt_verifier,
            base_url="https://fastmcp.com",
        )

        assert proxy.client_registration_options is not None
        assert proxy.client_registration_options.enabled is True