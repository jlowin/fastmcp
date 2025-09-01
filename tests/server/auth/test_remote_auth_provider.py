import httpx
import pytest
from pydantic import AnyHttpUrl

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, RemoteAuthProvider, TokenVerifier


class SimpleTokenVerifier(TokenVerifier):
    """Simple token verifier for testing."""

    def __init__(self, valid_tokens: dict[str, AccessToken] | None = None):
        super().__init__()
        self.valid_tokens = valid_tokens or {}

    async def verify_token(self, token: str) -> AccessToken | None:
        return self.valid_tokens.get(token)


class TestRemoteAuthProvider:
    """Test suite for RemoteAuthProvider."""

    def test_init(self):
        """Test RemoteAuthProvider initialization."""
        token_verifier = SimpleTokenVerifier()
        auth_servers = [AnyHttpUrl("https://auth.example.com")]

        provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=auth_servers,
            base_url="https://api.example.com",
        )

        assert provider.token_verifier is token_verifier
        assert provider.authorization_servers == auth_servers
        assert provider.base_url == AnyHttpUrl("https://api.example.com/")

    async def test_verify_token_delegates_to_verifier(self):
        """Test that verify_token delegates to the token verifier."""
        access_token = AccessToken(
            token="valid_token", client_id="test-client", scopes=[]
        )
        token_verifier = SimpleTokenVerifier({"valid_token": access_token})

        provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        # Valid token
        result = await provider.verify_token("valid_token")
        assert result is access_token

        # Invalid token
        result = await provider.verify_token("invalid_token")
        assert result is None

    def test_get_routes_creates_protected_resource_routes(self):
        """Test that get_routes creates protected resource routes."""
        token_verifier = SimpleTokenVerifier()
        auth_servers = [AnyHttpUrl("https://auth.example.com")]

        provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=auth_servers,
            base_url="https://api.example.com",
        )

        routes = provider.get_routes()
        assert len(routes) == 1

        # Check that the route is the OAuth protected resource metadata endpoint
        route = routes[0]
        assert route.path == "/.well-known/oauth-protected-resource"
        assert route.methods is not None
        assert "GET" in route.methods

    def test_get_resource_url_with_well_known_path(self):
        """Test _get_resource_url returns correct URL for .well-known path."""
        provider = RemoteAuthProvider(
            token_verifier=SimpleTokenVerifier(),
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        metadata_url = provider._get_resource_url(
            "/.well-known/oauth-protected-resource"
        )
        assert metadata_url == AnyHttpUrl(
            "https://api.example.com/.well-known/oauth-protected-resource"
        )

    def test_get_resource_url_handles_trailing_slash(self):
        """Test _get_resource_url handles trailing slash correctly."""
        provider = RemoteAuthProvider(
            token_verifier=SimpleTokenVerifier(),
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com/",
        )

        metadata_url = provider._get_resource_url(
            "/.well-known/oauth-protected-resource"
        )
        assert metadata_url == AnyHttpUrl(
            "https://api.example.com/.well-known/oauth-protected-resource"
        )


class TestRemoteAuthProviderIntegration:
    """Integration tests for RemoteAuthProvider with FastMCP server."""

    async def test_protected_resource_metadata_endpoint_status_code(self):
        """Test that the protected resource metadata endpoint returns 200."""
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://api.example.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")
            assert response.status_code == 200

    async def test_protected_resource_metadata_endpoint_resource_field(self):
        """Test that the protected resource metadata endpoint returns correct resource field."""
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://api.example.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")
            data = response.json()

            # This is the key test - ensure resource field contains the full MCP URL
            assert data["resource"] == "https://api.example.com/mcp"

    async def test_protected_resource_metadata_endpoint_authorization_servers_field(
        self,
    ):
        """Test that the protected resource metadata endpoint returns correct authorization_servers field."""
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://api.example.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")
            data = response.json()

            assert data["authorization_servers"] == ["https://auth.example.com/"]

    @pytest.mark.parametrize(
        "base_url,expected_resource",
        [
            ("https://api.example.com", "https://api.example.com/mcp"),
            ("https://api.example.com/", "https://api.example.com/mcp"),
        ],
    )
    async def test_base_url_configurations(self, base_url: str, expected_resource: str):
        """Test different base_url configurations."""
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url=base_url,
        )
        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://test.example.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")

            assert response.status_code == 200
            data = response.json()
            assert data["resource"] == expected_resource

    async def test_multiple_authorization_servers_resource_field(self):
        """Test resource field with multiple authorization servers."""
        token_verifier = SimpleTokenVerifier()
        auth_servers = [
            AnyHttpUrl("https://auth1.example.com"),
            AnyHttpUrl("https://auth2.example.com"),
        ]

        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=auth_servers,
            base_url="https://api.example.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://api.example.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")

            data = response.json()
            assert data["resource"] == "https://api.example.com/mcp"

    async def test_multiple_authorization_servers_list(self):
        """Test authorization_servers field with multiple authorization servers."""
        token_verifier = SimpleTokenVerifier()
        auth_servers = [
            AnyHttpUrl("https://auth1.example.com"),
            AnyHttpUrl("https://auth2.example.com"),
        ]

        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=auth_servers,
            base_url="https://api.example.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://api.example.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")

            data = response.json()
            assert set(data["authorization_servers"]) == {
                "https://auth1.example.com/",
                "https://auth2.example.com/",
            }

    async def test_token_verification_with_valid_auth_succeeds(self):
        """Test that requests with valid auth token succeed."""
        # Note: This test focuses on HTTP-level authentication behavior
        # For the RemoteAuthProvider, the key test is that the OAuth discovery
        # endpoint correctly reports the resource server URL, which is tested above

        # This is primarily testing that the token verifier integration works
        access_token = AccessToken(
            token="valid_token", client_id="test-client", scopes=[]
        )
        token_verifier = SimpleTokenVerifier({"valid_token": access_token})

        provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        # Test that the provider correctly delegates to the token verifier
        result = await provider.verify_token("valid_token")
        assert result is access_token

        result = await provider.verify_token("invalid_token")
        assert result is None

    async def test_token_verification_with_invalid_auth_fails(self):
        """Test that the provider correctly rejects invalid tokens."""
        access_token = AccessToken(
            token="valid_token", client_id="test-client", scopes=[]
        )
        token_verifier = SimpleTokenVerifier({"valid_token": access_token})

        provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://auth.example.com")],
            base_url="https://api.example.com",
        )

        # Test that invalid tokens are rejected
        result = await provider.verify_token("invalid_token")
        assert result is None

    async def test_issue_1348_oauth_discovery_returns_correct_url(self):
        """Test that RemoteAuthProvider correctly returns the full MCP endpoint URL.

        This test confirms that RemoteAuthProvider works correctly and returns
        the resource URL with the MCP path appended to the base URL.
        """
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://accounts.google.com")],
            base_url="https://my-server.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://my-server.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")

            assert response.status_code == 200
            data = response.json()

            # The RemoteAuthProvider correctly returns the full MCP endpoint URL
            assert data["resource"] == "https://my-server.com/mcp"
            assert data["authorization_servers"] == ["https://accounts.google.com/"]

    async def test_resource_name_field(self):
        """Test that RemoteAuthProvider correctly returns the resource_name.

        This test confirms that RemoteAuthProvider works correctly and returns
        the exact resource_name specified.
        """
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://accounts.google.com")],
            base_url="https://my-server.com",
            resource_name="My Test Resource",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://my-server.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")

            assert response.status_code == 200
            data = response.json()

            # The RemoteAuthProvider correctly returns the resource_name
            assert data["resource_name"] == "My Test Resource"

    async def test_resource_documentation_field(self):
        """Test that RemoteAuthProvider correctly returns the resource_documentation.

        This test confirms that RemoteAuthProvider works correctly and returns
        the exact resource_documentation specified.
        """
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://accounts.google.com")],
            base_url="https://my-server.com",
            resource_documentation=AnyHttpUrl(
                "https://doc.my-server.com/resource-docs"
            ),
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://my-server.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")

            assert response.status_code == 200
            data = response.json()

            # The RemoteAuthProvider correctly returns the resource_documentation
            assert (
                data["resource_documentation"]
                == "https://doc.my-server.com/resource-docs"
            )

    async def test_www_authenticate_header_points_to_base_url(self):
        """Test that WWW-Authenticate header always points to base URL's .well-known.

        This test verifies the fix for issue #1685 where the WWW-Authenticate header
        was incorrectly including the MCP path in the .well-known URL.
        """
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://accounts.google.com")],
            base_url="https://my-server.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        # Mount MCP at a non-root path
        mcp_http_app = mcp.http_app(path="/api/v1/mcp")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://my-server.com",
        ) as client:
            # Make unauthorized request to MCP endpoint
            response = await client.get("/api/v1/mcp")
            assert response.status_code == 401

            www_auth = response.headers.get("www-authenticate", "")
            assert "resource_metadata=" in www_auth

            # Extract the metadata URL from the header
            import re

            match = re.search(r'resource_metadata="([^"]+)"', www_auth)
            assert match is not None
            metadata_url = match.group(1)

            # Should point to base URL, not include /api/v1/mcp
            assert (
                metadata_url
                == "https://my-server.com/.well-known/oauth-protected-resource"
            )

    async def test_automatic_resource_url_capture(self):
        """Test that resource URL is automatically captured from MCP path.

        This test verifies PR #1682 functionality where the resource URL
        should be automatically set based on the MCP endpoint path.
        """
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://accounts.google.com")],
            base_url="https://my-server.com",
            # Note: NOT specifying resource_server_url
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        # Mount MCP at a specific path
        mcp_http_app = mcp.http_app(path="/mcp")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://my-server.com",
        ) as client:
            # Get the .well-known metadata
            response = await client.get("/.well-known/oauth-protected-resource")
            assert response.status_code == 200

            data = response.json()
            # The resource URL should be automatically set to the MCP path
            assert data.get("resource") == "https://my-server.com/mcp"

    async def test_automatic_resource_url_with_nested_path(self):
        """Test automatic resource URL capture with deeply nested MCP path."""
        token_verifier = SimpleTokenVerifier()
        auth_provider = RemoteAuthProvider(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl("https://accounts.google.com")],
            base_url="https://my-server.com",
        )

        mcp = FastMCP("test-server", auth=auth_provider)
        mcp_http_app = mcp.http_app(path="/api/v2/services/mcp")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url="https://my-server.com",
        ) as client:
            response = await client.get("/.well-known/oauth-protected-resource")
            assert response.status_code == 200

            data = response.json()
            # Should automatically capture the nested path
            assert data.get("resource") == "https://my-server.com/api/v2/services/mcp"
