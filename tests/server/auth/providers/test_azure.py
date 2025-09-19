"""Tests for Azure (Microsoft Entra) OAuth provider."""

import os
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.azure import AzureProvider


class TestAzureProvider:
    """Test Azure OAuth provider functionality."""

    def test_init_with_explicit_params(self):
        """Test AzureProvider initialization with explicit parameters."""
        provider = AzureProvider(
            client_id="12345678-1234-1234-1234-123456789012",
            client_secret="azure_secret_123",
            tenant_id="87654321-4321-4321-4321-210987654321",
            base_url="https://myserver.com",
            required_scopes=["User.Read", "Mail.Read"],
        )

        assert provider._upstream_client_id == "12345678-1234-1234-1234-123456789012"
        assert provider._upstream_client_secret.get_secret_value() == "azure_secret_123"
        assert str(provider.base_url) == "https://myserver.com/"
        # Check tenant is in the endpoints
        parsed_auth = urlparse(provider._upstream_authorization_endpoint)
        assert "87654321-4321-4321-4321-210987654321" in parsed_auth.path
        parsed_token = urlparse(provider._upstream_token_endpoint)
        assert "87654321-4321-4321-4321-210987654321" in parsed_token.path

    @pytest.mark.parametrize(
        "scopes_env",
        [
            "User.Read,Calendar.Read",
            '["User.Read", "Calendar.Read"]',
        ],
    )
    def test_init_with_env_vars(self, scopes_env):
        """Test AzureProvider initialization from environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_AZURE_CLIENT_ID": "env-client-id",
                "FASTMCP_SERVER_AUTH_AZURE_CLIENT_SECRET": "env-secret",
                "FASTMCP_SERVER_AUTH_AZURE_TENANT_ID": "env-tenant-id",
                "FASTMCP_SERVER_AUTH_AZURE_BASE_URL": "https://envserver.com",
                "FASTMCP_SERVER_AUTH_AZURE_REQUIRED_SCOPES": scopes_env,
            },
        ):
            provider = AzureProvider()

            assert provider._upstream_client_id == "env-client-id"
            assert provider._upstream_client_secret.get_secret_value() == "env-secret"
            assert str(provider.base_url) == "https://envserver.com/"
            assert provider._token_validator.required_scopes == [
                "User.Read",
                "Calendar.Read",
            ]
            # Check tenant is in the endpoints
            parsed_auth = urlparse(provider._upstream_authorization_endpoint)
            assert "env-tenant-id" in parsed_auth.path
            parsed_token = urlparse(provider._upstream_token_endpoint)
            assert "env-tenant-id" in parsed_token.path

    def test_init_missing_client_id_raises_error(self):
        """Test that missing client_id raises ValueError."""
        with pytest.raises(ValueError, match="client_id is required"):
            AzureProvider(
                client_secret="test_secret",
                tenant_id="test-tenant",
            )

    def test_init_missing_client_secret_raises_error(self):
        """Test that missing client_secret raises ValueError."""
        with pytest.raises(ValueError, match="client_secret is required"):
            AzureProvider(
                client_id="test_client",
                tenant_id="test-tenant",
            )

    def test_init_missing_tenant_id_raises_error(self):
        """Test that missing tenant_id raises ValueError."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            AzureProvider(
                client_id="test_client",
                client_secret="test_secret",
            )

    def test_init_defaults(self):
        """Test that default values are applied correctly."""
        provider = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="test-tenant",
        )

        # Check defaults
        assert provider.base_url is None
        assert provider._redirect_path == "/auth/callback"
        # Azure provider defaults are set but we can't easily verify them without accessing internals

    def test_oauth_endpoints_configured_correctly(self):
        """Test that OAuth endpoints are configured correctly."""
        provider = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="my-tenant-id",
            base_url="https://myserver.com",
        )

        # Check that endpoints use the correct Azure OAuth2 v2.0 endpoints with tenant
        assert (
            provider._upstream_authorization_endpoint
            == "https://login.microsoftonline.com/my-tenant-id/oauth2/v2.0/authorize"
        )
        assert (
            provider._upstream_token_endpoint
            == "https://login.microsoftonline.com/my-tenant-id/oauth2/v2.0/token"
        )
        assert (
            provider._upstream_revocation_endpoint is None
        )  # Azure doesn't support revocation

    def test_special_tenant_values(self):
        """Test that special tenant values are accepted."""
        # Test with "organizations"
        provider1 = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="organizations",
        )
        parsed = urlparse(provider1._upstream_authorization_endpoint)
        assert "/organizations/" in parsed.path

        # Test with "consumers"
        provider2 = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="consumers",
        )
        parsed = urlparse(provider2._upstream_authorization_endpoint)
        assert "/consumers/" in parsed.path

    def test_azure_specific_scopes(self):
        """Test handling of Azure-specific scope formats."""
        # Just test that the provider accepts Azure-specific scopes without error
        provider = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="test-tenant",
            required_scopes=[
                "User.Read",
                "Mail.Read",
                "Calendar.ReadWrite",
                "openid",
                "profile",
            ],
        )

        # Provider should initialize successfully with these scopes
        assert provider is not None

    async def test_authorize_filters_resource_parameter(self):
        """Test that authorize method filters out the 'resource' parameter for Azure AD v2.0."""

        provider = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="test-tenant",
            base_url="https://myserver.com",
        )

        # Create a mock client
        client = OAuthClientInformationFull(
            client_id="test_client_123",
            client_secret="client_secret_456",
            redirect_uris=[AnyUrl("http://localhost:12345/callback")],
            grant_types=["authorization_code"],
            scope="openid profile",
        )

        # Create authorization params with resource parameter (which Azure v2.0 doesn't support)
        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:12345/callback"),
            redirect_uri_provided_explicitly=True,
            state="test_state_123",
            code_challenge="test_challenge",
            code_challenge_method="S256",
            scopes=["openid", "profile"],
            resource="https://graph.microsoft.com",  # This should be filtered out
        )

        # Mock the parent class's authorize method
        with patch.object(
            OAuthProxy,
            "authorize",
            new_callable=AsyncMock,
            return_value="https://login.microsoftonline.com/test-tenant/oauth2/v2.0/authorize?test=1",
        ) as mock_authorize:
            # Call the Azure provider's authorize method
            await provider.authorize(client, params)

            # Verify the parent's authorize was called
            mock_authorize.assert_called_once()

            # Get the params that were passed to the parent's authorize
            call_args = mock_authorize.call_args
            called_client = call_args[0][0]
            called_params = call_args[0][1]

            # Verify the resource parameter was filtered out
            assert (
                not hasattr(called_params, "resource") or called_params.resource is None
            ), "Resource parameter should have been filtered out"

            # Verify other parameters were preserved
            assert called_params.redirect_uri == params.redirect_uri
            assert (
                called_params.redirect_uri_provided_explicitly
                == params.redirect_uri_provided_explicitly
            )
            assert called_params.state == params.state
            assert called_params.code_challenge == params.code_challenge
            assert called_params.scopes == params.scopes

            # Verify the client was passed through unchanged
            assert called_client == client

    async def test_authorize_without_resource_parameter(self):
        """Test that authorize works normally when no resource parameter is present."""

        provider = AzureProvider(
            client_id="test_client",
            client_secret="test_secret",
            tenant_id="test-tenant",
            base_url="https://myserver.com",
        )

        # Create a mock client
        client = OAuthClientInformationFull(
            client_id="test_client_123",
            client_secret="client_secret_456",
            redirect_uris=[AnyUrl("http://localhost:12345/callback")],
            grant_types=["authorization_code"],
            scope="openid profile",
        )

        # Create authorization params WITHOUT resource parameter
        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:12345/callback"),
            redirect_uri_provided_explicitly=True,
            state="test_state_123",
            code_challenge="test_challenge",
            code_challenge_method="S256",
            scopes=["openid", "profile"],
            # No resource parameter
        )

        # Mock the parent class's authorize method
        with patch.object(
            OAuthProxy,
            "authorize",
            new_callable=AsyncMock,
            return_value="https://login.microsoftonline.com/test-tenant/oauth2/v2.0/authorize?test=1",
        ) as mock_authorize:
            # Call should work without issues
            result = await provider.authorize(client, params)

            # Verify the parent's authorize was called
            mock_authorize.assert_called_once()
            assert result is not None
