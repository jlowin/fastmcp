import pytest
from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route
from starlette.testclient import TestClient

from fastmcp.server import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair
from fastmcp.server.http import create_streamable_http_app


class TestStreamableHTTPAppResourceMetadataURL:
    """Test resource_metadata_url logic in create_streamable_http_app."""

    @pytest.fixture
    def rsa_key_pair(self) -> RSAKeyPair:
        """Generate RSA key pair for testing."""
        return RSAKeyPair.generate()

    @pytest.fixture
    def bearer_auth_provider(self, rsa_key_pair):
        provider = JWTVerifier(
            public_key=rsa_key_pair.public_key,
            issuer="https://issuer",
            audience="https://audience",
            base_url="https://resource.example.com",
        )
        return provider

    def test_auth_endpoint_wrapped_with_cors_middleware(self, bearer_auth_provider):
        """Test that auth-protected endpoints are wrapped with CORS middleware."""
        server = FastMCP(name="TestServer")

        app = create_streamable_http_app(
            server=server,
            streamable_http_path="/mcp",
            auth=bearer_auth_provider,
        )

        route = next(r for r in app.routes if isinstance(r, Route) and r.path == "/mcp")

        # When auth is enabled, endpoint should be wrapped with CORSMiddleware
        assert isinstance(route.endpoint, CORSMiddleware)
        # Verify allowed methods include OPTIONS for CORS preflight
        assert "OPTIONS" in route.methods

    def test_auth_endpoint_has_correct_methods(self, rsa_key_pair):
        """Test that auth-protected endpoints have correct HTTP methods including OPTIONS."""
        provider = JWTVerifier(
            public_key=rsa_key_pair.public_key,
            issuer="https://issuer",
            audience="https://audience",
            base_url="https://resource.example.com/",
        )
        server = FastMCP(name="TestServer")
        app = create_streamable_http_app(
            server=server,
            streamable_http_path="/mcp",
            auth=provider,
        )
        route = next(r for r in app.routes if isinstance(r, Route) and r.path == "/mcp")

        # Verify CORSMiddleware is applied
        assert isinstance(route.endpoint, CORSMiddleware)
        # Verify methods include GET, POST, DELETE, OPTIONS for streamable-http
        expected_methods = {"GET", "POST", "DELETE", "OPTIONS"}
        assert expected_methods.issubset(set(route.methods))

    def test_no_auth_provider_mounts_without_cors_middleware(self, rsa_key_pair):
        """Test that endpoints without auth are not wrapped with CORS middleware."""
        server = FastMCP(name="TestServer")
        app = create_streamable_http_app(
            server=server,
            streamable_http_path="/mcp",
            auth=None,
        )
        route = next(r for r in app.routes if isinstance(r, Route) and r.path == "/mcp")
        # Without auth, no CORSMiddleware or RequireAuthMiddleware should be applied
        assert not isinstance(route.endpoint, CORSMiddleware)
        assert not isinstance(route.endpoint, RequireAuthMiddleware)

    def test_options_request_succeeds_with_auth(self, bearer_auth_provider):
        """Test that OPTIONS requests to /mcp succeed even when auth is required."""
        server = FastMCP(name="TestServer")
        app = create_streamable_http_app(
            server=server,
            streamable_http_path="/mcp",
            auth=bearer_auth_provider,
        )

        # Test OPTIONS request with proper CORS preflight headers
        with TestClient(app) as client:
            response = client.options(
                "/mcp",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert response.status_code == 200
            # Verify CORS headers are present
            assert "access-control-allow-origin" in response.headers
            assert "access-control-allow-methods" in response.headers

    def test_authenticated_requests_still_require_auth(self, bearer_auth_provider):
        """Test that actual requests (not OPTIONS) still require authentication."""
        server = FastMCP(name="TestServer")
        app = create_streamable_http_app(
            server=server,
            streamable_http_path="/mcp",
            auth=bearer_auth_provider,
        )

        # Test POST request without auth - should fail with 401
        with TestClient(app) as client:
            response = client.post("/mcp")
            assert response.status_code == 401
            assert "www-authenticate" in response.headers
