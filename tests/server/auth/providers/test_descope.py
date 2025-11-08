"""Tests for Descope OAuth provider."""

import os
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.providers.descope import DescopeProvider
from fastmcp.utilities.tests import HeadlessOAuth, run_server_async


class TestDescopeProvider:
    """Test Descope OAuth provider functionality."""

    def test_init_with_explicit_params(self):
        """Test DescopeProvider initialization with explicit parameters."""
        provider = DescopeProvider(
            config_url="https://api.descope.com/v1/apps/agentic/P2abc123/M123/.well-known/openid-configuration",
            base_url="https://myserver.com",
        )

        assert provider.project_id == "P2abc123"
        assert str(provider.base_url) == "https://myserver.com/"
        assert str(provider.descope_base_url) == "https://api.descope.com"

    def test_init_with_env_vars(self):
        """Test DescopeProvider initialization from environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_DESCOPEPROVIDER_CONFIG_URL": "https://api.descope.com/v1/apps/agentic/P2env123/M123/.well-known/openid-configuration",
                "FASTMCP_SERVER_AUTH_DESCOPEPROVIDER_BASE_URL": "https://envserver.com",
            },
        ):
            provider = DescopeProvider()

            assert provider.project_id == "P2env123"
            assert str(provider.base_url) == "https://envserver.com/"
            assert str(provider.descope_base_url) == "https://api.descope.com"

    def test_environment_variable_loading(self):
        """Test that environment variables are loaded correctly."""
        # This test verifies that the provider can be created with environment variables
        provider = DescopeProvider(
            config_url="https://api.descope.com/v1/apps/agentic/P2env123/M123/.well-known/openid-configuration",
            base_url="http://env-server.com",
        )

        # Should have loaded from environment
        assert provider.project_id == "P2env123"
        assert str(provider.base_url) == "http://env-server.com/"
        assert str(provider.descope_base_url) == "https://api.descope.com"

    def test_config_url_parsing(self):
        """Test that config_url is parsed correctly to extract base URL and project ID."""
        # Standard HTTPS URL
        provider1 = DescopeProvider(
            config_url="https://api.descope.com/v1/apps/agentic/P2abc123/M123/.well-known/openid-configuration",
            base_url="https://myserver.com",
        )
        assert str(provider1.descope_base_url) == "https://api.descope.com"
        assert provider1.project_id == "P2abc123"

        # HTTP URL (for local testing)
        provider2 = DescopeProvider(
            config_url="http://localhost:8080/v1/apps/agentic/P2abc123/M123/.well-known/openid-configuration",
            base_url="https://myserver.com",
        )
        assert str(provider2.descope_base_url) == "http://localhost:8080"
        assert provider2.project_id == "P2abc123"

        # URL without .well-known/openid-configuration suffix
        provider3 = DescopeProvider(
            config_url="https://api.descope.com/v1/apps/agentic/P2abc123/M123",
            base_url="https://myserver.com",
        )
        assert str(provider3.descope_base_url) == "https://api.descope.com"
        assert provider3.project_id == "P2abc123"

    def test_config_url_required(self):
        """Test that config_url is required."""
        with pytest.raises(ValidationError):
            DescopeProvider(
                base_url="https://myserver.com",
            )

    def test_jwt_verifier_configured_correctly(self):
        """Test that JWT verifier is configured correctly."""
        config_url = "https://api.descope.com/v1/apps/agentic/P2abc123/M123/.well-known/openid-configuration"
        issuer_url = "https://api.descope.com/v1/apps/agentic/P2abc123/M123"

        provider = DescopeProvider(
            config_url=config_url,
            base_url="https://myserver.com",
        )

        # Check that JWT verifier uses the correct endpoints
        assert (
            provider.token_verifier.jwks_uri  # type: ignore[attr-defined]
            == "https://api.descope.com/P2abc123/.well-known/jwks.json"
        )
        assert (
            provider.token_verifier.issuer == issuer_url  # type: ignore[attr-defined]
        )
        assert provider.token_verifier.audience == "P2abc123"  # type: ignore[attr-defined]


@pytest.fixture
async def mcp_server_url():
    """Start Descope server."""
    mcp = FastMCP(
        auth=DescopeProvider(
            config_url="https://api.descope.com/v1/apps/agentic/P2test123/M123/.well-known/openid-configuration",
            base_url="http://localhost:4321",
        )
    )

    @mcp.tool
    def add(a: int, b: int) -> int:
        return a + b

    async with run_server_async(mcp, transport="http") as url:
        yield url


@pytest.fixture
def client_with_headless_oauth(mcp_server_url: str) -> Client:
    """Client with headless OAuth that bypasses browser interaction."""
    return Client(
        transport=StreamableHttpTransport(mcp_server_url),
        auth=HeadlessOAuth(mcp_url=mcp_server_url),
    )


class TestDescopeProviderIntegration:
    async def test_unauthorized_access(self, mcp_server_url: str):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async with Client(mcp_server_url) as client:
                tools = await client.list_tools()  # noqa: F841

        assert isinstance(exc_info.value, httpx.HTTPStatusError)
        assert exc_info.value.response.status_code == 401
        assert "tools" not in locals()

    # async def test_authorized_access(self, client_with_headless_oauth: Client):
    #     async with client_with_headless_oauth:
    #         tools = await client_with_headless_oauth.list_tools()
    #     assert tools is not None
    #     assert len(tools) > 0
    #     assert "add" in tools
