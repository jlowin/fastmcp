"""Unit tests for Keycloak OAuth provider - Fixed version."""

import os
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from fastmcp import FastMCP
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.keycloak import (
    KeycloakAuthProvider,
    KeycloakProviderSettings,
)

TEST_REALM_URL = "https://keycloak.example.com/realms/test"
TEST_BASE_URL = "https://example.com:8000"
TEST_REQUIRED_SCOPES = ["openid", "profile"]


@pytest.fixture
def valid_oidc_configuration_dict():
    """Create a valid OIDC configuration dict for testing."""
    return {
        "issuer": TEST_REALM_URL,
        "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
        "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
        "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
        "registration_endpoint": f"{TEST_REALM_URL}/clients-registrations/openid-connect",
        "response_types_supported": ["code", "id_token", "token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@pytest.fixture
def mock_oidc_config(valid_oidc_configuration_dict):
    """Create a mock OIDCConfiguration object."""
    return OIDCConfiguration.model_validate(valid_oidc_configuration_dict)


def create_minimal_oidc_config():
    """Create a minimal valid OIDC configuration for testing."""
    return OIDCConfiguration.model_validate(
        {
            "issuer": TEST_REALM_URL,
            "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
            "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
            "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    )


class TestKeycloakProviderSettings:
    """Test settings for Keycloak OAuth provider."""

    def test_settings_from_env_vars(self):
        """Test that settings can be loaded from environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL": TEST_REALM_URL,
                "FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL": TEST_BASE_URL,
                "FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES": ",".join(
                    TEST_REQUIRED_SCOPES
                ),
            },
        ):
            # Let environment variables populate the settings
            settings = KeycloakProviderSettings.model_validate({})

            assert str(settings.realm_url) == TEST_REALM_URL
            assert str(settings.base_url).rstrip("/") == TEST_BASE_URL
            assert settings.required_scopes == TEST_REQUIRED_SCOPES

    def test_settings_explicit_override_env(self):
        """Test that explicit settings override environment variables."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL": TEST_REALM_URL,
                "FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL": TEST_BASE_URL,
            },
        ):
            settings = KeycloakProviderSettings.model_validate(
                {
                    "realm_url": "https://explicit.keycloak.com/realms/explicit",
                    "base_url": "https://explicit.example.com",
                }
            )

            assert (
                str(settings.realm_url)
                == "https://explicit.keycloak.com/realms/explicit"
            )
            assert str(settings.base_url).rstrip("/") == "https://explicit.example.com"

    @pytest.mark.parametrize(
        "scopes_env",
        [
            "openid,profile",
            '["openid", "profile"]',
        ],
    )
    def test_settings_parse_scopes(self, scopes_env):
        """Test that scopes are parsed correctly from different formats."""
        with patch.dict(
            os.environ,
            {
                "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL": TEST_REALM_URL,
                "FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL": TEST_BASE_URL,
                "FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES": scopes_env,
            },
        ):
            # Let environment variables populate the settings
            settings = KeycloakProviderSettings.model_validate({})
            assert settings.required_scopes == ["openid", "profile"]


class TestKeycloakAuthProvider:
    """Test KeycloakAuthProvider initialization."""

    def test_init_with_explicit_params(self, mock_oidc_config):
        """Test initialization with explicit parameters."""
        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = mock_oidc_config

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

            mock_discover.assert_called_once()

            assert provider.realm_url == TEST_REALM_URL
            assert str(provider.base_url) == TEST_BASE_URL + "/"
            assert isinstance(provider.token_verifier, JWTVerifier)
            assert provider.token_verifier.required_scopes == TEST_REQUIRED_SCOPES

    def test_init_with_env_vars(self, mock_oidc_config):
        """Test initialization with environment variables."""
        with (
            patch.dict(
                os.environ,
                {
                    "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL": TEST_REALM_URL,
                    "FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL": TEST_BASE_URL,
                    "FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES": ",".join(
                        TEST_REQUIRED_SCOPES
                    ),
                },
            ),
            patch.object(
                KeycloakAuthProvider, "_discover_oidc_configuration"
            ) as mock_discover,
        ):
            mock_discover.return_value = mock_oidc_config

            provider = KeycloakAuthProvider()

            mock_discover.assert_called_once()

            assert provider.realm_url == TEST_REALM_URL
            assert str(provider.base_url) == TEST_BASE_URL + "/"
            assert provider.token_verifier.required_scopes == TEST_REQUIRED_SCOPES

    def test_init_with_custom_token_verifier(self, mock_oidc_config):
        """Test initialization with custom token verifier."""
        custom_verifier = JWTVerifier(
            jwks_uri=f"{TEST_REALM_URL}/.well-known/jwks.json",
            issuer=TEST_REALM_URL,
            audience="custom-client-id",
            required_scopes=["custom:scope"],
        )

        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = mock_oidc_config

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                token_verifier=custom_verifier,
            )

            assert provider.token_verifier is custom_verifier
            assert provider.token_verifier.audience == "custom-client-id"
            assert provider.token_verifier.required_scopes == ["custom:scope"]


class TestKeycloakOIDCDiscovery:
    """Test OIDC configuration discovery."""

    def test_discover_oidc_configuration_success(self, valid_oidc_configuration_dict):
        """Test successful OIDC configuration discovery."""
        with patch(
            "fastmcp.server.auth.oidc_proxy.OIDCConfiguration.get_oidc_configuration"
        ) as mock_get:
            mock_config = OIDCConfiguration.model_validate(
                valid_oidc_configuration_dict
            )
            mock_get.return_value = mock_config

            KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
            )

            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert (
                str(call_args[0][0])
                == f"{TEST_REALM_URL}/.well-known/openid-configuration"
            )
            assert call_args[1]["strict"] is False

    def test_discover_oidc_configuration_with_defaults(self):
        """Test OIDC configuration discovery with default values."""
        # Create a minimal config with only required fields but missing optional ones
        minimal_config = {
            "issuer": TEST_REALM_URL,
            "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
            "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
            "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",  # Required field
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            # Missing registration_endpoint - this should get default
        }

        with patch(
            "fastmcp.server.auth.oidc_proxy.OIDCConfiguration.get_oidc_configuration"
        ) as mock_get:
            mock_config = OIDCConfiguration.model_validate(minimal_config)
            mock_get.return_value = mock_config

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
            )

            # Check that defaults were applied for missing optional fields
            config = provider.oidc_config
            assert config.jwks_uri == f"{TEST_REALM_URL}/.well-known/jwks.json"
            assert config.issuer == TEST_REALM_URL
            assert (
                config.registration_endpoint
                == f"{TEST_REALM_URL}/clients-registrations/openid-connect"
            )


class TestKeycloakRoutes:
    """Test Keycloak auth provider routes."""

    @pytest.fixture
    def keycloak_provider(self, mock_oidc_config):
        """Create a KeycloakAuthProvider for testing."""
        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = mock_oidc_config
            return KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

    def test_get_routes_includes_all_endpoints(self, keycloak_provider):
        """Test that get_routes returns all required endpoints."""
        routes = keycloak_provider.get_routes()

        # Should have RemoteAuthProvider routes plus Keycloak-specific ones
        assert len(routes) >= 4

        paths = [route.path for route in routes]
        assert "/.well-known/oauth-protected-resource" in paths
        assert "/.well-known/oauth-authorization-server" in paths
        assert "/register" in paths
        assert "/authorize" in paths

    async def test_oauth_authorization_server_metadata_endpoint(
        self, keycloak_provider
    ):
        """Test the OAuth authorization server metadata endpoint."""
        mcp = FastMCP("test-server", auth=keycloak_provider)
        mcp_http_app = mcp.http_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url=TEST_BASE_URL,
        ) as client:
            response = await client.get("/.well-known/oauth-authorization-server")

            assert response.status_code == 200
            data = response.json()

            # Check that the metadata includes FastMCP proxy endpoints
            assert data["registration_endpoint"] == f"{TEST_BASE_URL}/register"
            assert data["authorization_endpoint"] == f"{TEST_BASE_URL}/authorize"
            assert data["issuer"] == TEST_REALM_URL
            assert data["jwks_uri"] == f"{TEST_REALM_URL}/.well-known/jwks.json"


class TestKeycloakClientRegistrationProxy:
    """Test client registration proxy functionality."""

    @pytest.fixture
    def keycloak_provider(self, mock_oidc_config):
        """Create a KeycloakAuthProvider for testing."""
        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = mock_oidc_config
            return KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

    async def test_register_client_proxy_endpoint_exists(self, keycloak_provider):
        """Test that the client registration proxy endpoint exists."""
        mcp = FastMCP("test-server", auth=keycloak_provider)
        mcp_http_app = mcp.http_app()

        # Test that the endpoint exists by making a request
        # We'll expect it to fail due to missing mock, but should not be a 404
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url=TEST_BASE_URL,
        ) as client:
            response = await client.post(
                "/register",
                json={
                    "redirect_uris": ["http://localhost:8000/callback"],
                    "client_name": "test-client",
                },
            )

            # Should not be 404 (endpoint exists) but will be 500 due to no mock
            assert response.status_code != 404


class TestKeycloakAuthorizationProxy:
    """Test authorization proxy functionality."""

    @pytest.fixture
    def keycloak_provider(self, mock_oidc_config):
        """Create a KeycloakAuthProvider for testing."""
        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = mock_oidc_config
            return KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

    async def test_authorize_proxy_with_scope_injection(self, keycloak_provider):
        """Test authorization proxy with scope injection."""
        mcp = FastMCP("test-server", auth=keycloak_provider)
        mcp_http_app = mcp.http_app()

        params = {
            "client_id": "test-client",
            "redirect_uri": "http://localhost:8000/callback",
            "response_type": "code",
            "state": "test-state",
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mcp_http_app),
            base_url=TEST_BASE_URL,
            follow_redirects=False,
        ) as client:
            response = await client.get("/authorize", params=params)

            assert response.status_code == 302

            # Parse the redirect URL
            location = response.headers["location"]
            parsed_url = urlparse(location)
            query_params = parse_qs(parsed_url.query)

            # Check that scope was injected
            assert "scope" in query_params
            injected_scopes = query_params["scope"][0].split(" ")
            assert set(injected_scopes) == set(TEST_REQUIRED_SCOPES)

            # Check other parameters are preserved
            assert query_params["client_id"][0] == "test-client"
            assert query_params["redirect_uri"][0] == "http://localhost:8000/callback"
            assert query_params["response_type"][0] == "code"
            assert query_params["state"][0] == "test-state"


class TestKeycloakEdgeCases:
    """Test edge cases and error conditions for KeycloakAuthProvider."""

    def test_malformed_oidc_configuration_handling(self):
        """Test handling of OIDC configuration with missing optional fields."""
        # Create a config with all required fields but missing some optional ones
        config_with_missing_optionals = {
            "issuer": TEST_REALM_URL,
            "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
            "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
            "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",  # Required
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            # Missing registration_endpoint (optional)
        }

        with patch(
            "fastmcp.server.auth.oidc_proxy.OIDCConfiguration.get_oidc_configuration"
        ) as mock_get:
            # First return the config without optional fields
            mock_config = OIDCConfiguration.model_validate(
                config_with_missing_optionals
            )
            mock_get.return_value = mock_config

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
            )

            # Should apply defaults for missing optional fields
            config = provider.oidc_config
            assert config.jwks_uri == f"{TEST_REALM_URL}/.well-known/jwks.json"
            assert (
                config.registration_endpoint
                == f"{TEST_REALM_URL}/clients-registrations/openid-connect"
            )

    def test_empty_required_scopes_handling(self):
        """Test handling of empty required scopes."""
        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = create_minimal_oidc_config()

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=[],
            )

            assert provider.token_verifier.required_scopes == []

    def test_realm_url_with_trailing_slash(self):
        """Test handling of realm URL with trailing slash."""
        realm_url_with_slash = TEST_REALM_URL + "/"

        with patch.object(
            KeycloakAuthProvider, "_discover_oidc_configuration"
        ) as mock_discover:
            mock_discover.return_value = create_minimal_oidc_config()

            provider = KeycloakAuthProvider(
                realm_url=realm_url_with_slash,
                base_url=TEST_BASE_URL,
            )

            # Should normalize by removing trailing slash
            assert provider.realm_url == TEST_REALM_URL
