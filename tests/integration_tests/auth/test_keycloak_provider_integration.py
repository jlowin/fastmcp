"""Integration tests for Keycloak OAuth provider."""

import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from fastmcp import FastMCP
from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider

TEST_REALM_URL = "https://keycloak.example.com/realms/test"
TEST_BASE_URL = "https://fastmcp.example.com"
TEST_REQUIRED_SCOPES = ["openid", "profile", "email"]


@pytest.fixture
def mock_keycloak_server():
    """Create a mock Keycloak server for integration testing."""

    async def oidc_configuration(request):
        """Mock OIDC configuration endpoint."""
        config = {
            "issuer": TEST_REALM_URL,
            "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
            "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
            "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
            "registration_endpoint": f"{TEST_REALM_URL}/clients-registrations/openid-connect",
            "response_types_supported": ["code", "id_token", "token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "profile", "email"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
        }
        return JSONResponse(config)

    async def client_registration(request):
        """Mock client registration endpoint."""
        body = await request.json()
        client_info = {
            "client_id": "keycloak-generated-client-id",
            "client_secret": "keycloak-generated-client-secret",
            "token_endpoint_auth_method": "client_secret_basic",  # Keycloak default
            "response_types": ["code", "none"],  # Keycloak default
            "redirect_uris": body.get("redirect_uris", []),
            "scope": body.get("scope", "openid"),
            "grant_types": ["authorization_code", "refresh_token"],
        }
        return JSONResponse(client_info, status_code=201)

    routes = [
        Route("/.well-known/openid-configuration", oidc_configuration, methods=["GET"]),
        Route(
            "/clients-registrations/openid-connect",
            client_registration,
            methods=["POST"],
        ),
    ]

    app = Starlette(routes=routes)
    return app


class TestKeycloakProviderIntegration:
    """Integration tests for KeycloakAuthProvider with mock Keycloak server."""

    async def test_end_to_end_client_registration_flow(self, mock_keycloak_server):
        """Test complete client registration flow with mock Keycloak."""
        # Mock the OIDC configuration request to the real Keycloak
        with patch("httpx.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "issuer": TEST_REALM_URL,
                "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
                "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
                "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
                "registration_endpoint": f"{TEST_REALM_URL}/clients-registrations/openid-connect",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Create KeycloakAuthProvider
            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

            # Create FastMCP app with the provider
            mcp = FastMCP("test-server", auth=provider)
            mcp_http_app = mcp.http_app()

            # Mock the actual HTTP client post method
            with patch(
                "fastmcp.server.auth.providers.keycloak.httpx.AsyncClient.post"
            ) as mock_post:
                # Mock Keycloak's response to client registration
                mock_keycloak_response = Mock()
                mock_keycloak_response.status_code = 201
                mock_keycloak_response.json.return_value = {
                    "client_id": "keycloak-generated-client-id",
                    "client_secret": "keycloak-generated-client-secret",
                    "token_endpoint_auth_method": "client_secret_basic",
                    "response_types": ["code", "none"],
                    "redirect_uris": ["http://localhost:8000/callback"],
                }
                mock_keycloak_response.headers = {"content-type": "application/json"}
                mock_post.return_value = mock_keycloak_response

                # Test client registration through FastMCP proxy
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=mcp_http_app),
                    base_url=TEST_BASE_URL,
                ) as client:
                    registration_data = {
                        "redirect_uris": ["http://localhost:8000/callback"],
                        "client_name": "test-mcp-client",
                        "client_uri": "http://localhost:8000",
                    }

                    response = await client.post("/register", json=registration_data)

                    # Verify the endpoint processed the request successfully
                    assert response.status_code == 201
                    client_info = response.json()
                    assert "client_id" in client_info
                    assert "client_secret" in client_info

                    # Verify the mock was called (meaning the proxy forwarded the request)
                    mock_post.assert_called_once()

    async def test_oauth_discovery_endpoints_integration(self):
        """Test OAuth discovery endpoints work correctly together."""
        with patch("httpx.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "issuer": TEST_REALM_URL,
                "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
                "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
                "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
                "registration_endpoint": f"{TEST_REALM_URL}/clients-registrations/openid-connect",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

            mcp = FastMCP("test-server", auth=provider)
            mcp_http_app = mcp.http_app()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mcp_http_app),
                base_url=TEST_BASE_URL,
            ) as client:
                # Test authorization server metadata
                auth_server_response = await client.get(
                    "/.well-known/oauth-authorization-server"
                )
                assert auth_server_response.status_code == 200
                auth_data = auth_server_response.json()

                # Test protected resource metadata
                # Per RFC 9728, when the resource is at /mcp, the metadata endpoint is at /.well-known/oauth-protected-resource/mcp
                resource_response = await client.get(
                    "/.well-known/oauth-protected-resource/mcp"
                )
                assert resource_response.status_code == 200
                resource_data = resource_response.json()

                # Verify endpoints are consistent and correct
                assert (
                    auth_data["authorization_endpoint"] == f"{TEST_BASE_URL}/authorize"
                )
                assert auth_data["registration_endpoint"] == f"{TEST_BASE_URL}/register"
                assert auth_data["issuer"] == TEST_REALM_URL
                assert (
                    auth_data["jwks_uri"] == f"{TEST_REALM_URL}/.well-known/jwks.json"
                )

                assert resource_data["resource"] == f"{TEST_BASE_URL}/mcp"
                assert f"{TEST_BASE_URL}/" in resource_data["authorization_servers"]

    async def test_authorization_flow_with_real_parameters(self):
        """Test authorization flow with realistic OAuth parameters."""
        with patch("httpx.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "issuer": TEST_REALM_URL,
                "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
                "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
                "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

            mcp = FastMCP("test-server", auth=provider)
            mcp_http_app = mcp.http_app()

            # Realistic OAuth authorization parameters
            oauth_params = {
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "http://localhost:8000/auth/callback",
                "state": "random-state-string-12345",
                "code_challenge": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                "code_challenge_method": "S256",
                "nonce": "random-nonce-67890",
            }

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mcp_http_app),
                base_url=TEST_BASE_URL,
                follow_redirects=False,
            ) as client:
                response = await client.get("/authorize", params=oauth_params)

                assert response.status_code == 302
                location = response.headers["location"]

                # Parse redirect URL to verify parameters
                parsed = urlparse(location)
                query_params = parse_qs(parsed.query)

                # Verify all parameters are preserved
                assert query_params["response_type"][0] == "code"
                assert query_params["client_id"][0] == "test-client-id"
                assert (
                    query_params["redirect_uri"][0]
                    == "http://localhost:8000/auth/callback"
                )
                assert query_params["state"][0] == "random-state-string-12345"
                assert (
                    query_params["code_challenge"][0]
                    == "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
                )
                assert query_params["code_challenge_method"][0] == "S256"
                assert query_params["nonce"][0] == "random-nonce-67890"

                # Verify scope injection
                injected_scopes = query_params["scope"][0].split(" ")
                assert set(injected_scopes) == set(TEST_REQUIRED_SCOPES)

    async def test_error_handling_with_keycloak_unavailable(self):
        """Test error handling when Keycloak is unavailable."""
        # Mock network error when trying to discover OIDC configuration
        with patch("httpx.get") as mock_get:
            mock_get.side_effect = httpx.RequestError("Network error")

            with pytest.raises(Exception):  # Should raise some network/discovery error
                KeycloakAuthProvider(
                    realm_url=TEST_REALM_URL,
                    base_url=TEST_BASE_URL,
                )

    async def test_concurrent_client_registrations(self):
        """Test handling multiple concurrent client registrations."""
        with patch("httpx.get") as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "issuer": TEST_REALM_URL,
                "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
                "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
                "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
                "registration_endpoint": f"{TEST_REALM_URL}/clients-registrations/openid-connect",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            provider = KeycloakAuthProvider(
                realm_url=TEST_REALM_URL,
                base_url=TEST_BASE_URL,
                required_scopes=TEST_REQUIRED_SCOPES,
            )

            mcp = FastMCP("test-server", auth=provider)
            mcp_http_app = mcp.http_app()

            # Mock concurrent Keycloak responses
            with patch(
                "fastmcp.server.auth.providers.keycloak.httpx.AsyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Different responses for different clients
                responses = [
                    {
                        "client_id": f"client-{i}",
                        "client_secret": f"secret-{i}",
                        "token_endpoint_auth_method": "client_secret_basic",
                        "response_types": ["code", "none"],
                    }
                    for i in range(3)
                ]

                mock_responses = []
                for response in responses:
                    mock_resp = Mock()
                    mock_resp.status_code = 201
                    mock_resp.json.return_value = response
                    mock_resp.headers = {"content-type": "application/json"}
                    mock_responses.append(mock_resp)

                mock_client.post.side_effect = mock_responses

                # Make concurrent requests
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=mcp_http_app),
                    base_url=TEST_BASE_URL,
                ) as client:
                    registration_data = [
                        {
                            "redirect_uris": [f"http://localhost:800{i}/callback"],
                            "client_name": f"test-client-{i}",
                        }
                        for i in range(3)
                    ]

                    # Send concurrent requests
                    tasks = [
                        client.post("/register", json=data)
                        for data in registration_data
                    ]
                    responses = await asyncio.gather(*tasks)

                    # Verify all requests succeeded
                    for i, response in enumerate(responses):
                        assert response.status_code == 201
                        client_info = response.json()
                        assert "client_id" in client_info
                        assert "client_secret" in client_info


class TestKeycloakProviderEnvironmentConfiguration:
    """Test configuration from environment variables in integration context."""

    def test_provider_loads_all_settings_from_environment(self):
        """Test that provider can be fully configured from environment."""
        env_vars = {
            "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL": TEST_REALM_URL,
            "FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL": TEST_BASE_URL,
            "FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES": "openid,profile,email,custom:scope",
        }

        with (
            patch.dict(os.environ, env_vars),
            patch("httpx.get") as mock_get,
        ):
            mock_response = Mock()
            mock_response.json.return_value = {
                "issuer": TEST_REALM_URL,
                "authorization_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/auth",
                "token_endpoint": f"{TEST_REALM_URL}/protocol/openid-connect/token",
                "jwks_uri": f"{TEST_REALM_URL}/.well-known/jwks.json",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            # Should work with no explicit parameters
            provider = KeycloakAuthProvider()

            assert provider.realm_url == TEST_REALM_URL
            assert str(provider.base_url) == TEST_BASE_URL + "/"
            assert provider.token_verifier.required_scopes == [
                "openid",
                "profile",
                "email",
                "custom:scope",
            ]

    async def test_provider_works_in_production_like_environment(self):
        """Test provider configuration that mimics production deployment."""
        production_env = {
            "FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL": "https://auth.company.com/realms/production",
            "FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL": "https://api.company.com",
            "FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES": "openid,profile,email,api:read,api:write",
        }

        with (
            patch.dict(os.environ, production_env),
            patch("httpx.get") as mock_get,
        ):
            mock_response = Mock()
            mock_response.json.return_value = {
                "issuer": "https://auth.company.com/realms/production",
                "authorization_endpoint": "https://auth.company.com/realms/production/protocol/openid-connect/auth",
                "token_endpoint": "https://auth.company.com/realms/production/protocol/openid-connect/token",
                "jwks_uri": "https://auth.company.com/realms/production/.well-known/jwks.json",
                "registration_endpoint": "https://auth.company.com/realms/production/clients-registrations/openid-connect",
            }
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            provider = KeycloakAuthProvider()
            mcp = FastMCP("production-server", auth=provider)
            mcp_http_app = mcp.http_app()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mcp_http_app),
                base_url="https://api.company.com",
            ) as client:
                # Test discovery endpoints work
                response = await client.get("/.well-known/oauth-authorization-server")
                assert response.status_code == 200
                data = response.json()

                assert data["issuer"] == "https://auth.company.com/realms/production"
                assert (
                    data["authorization_endpoint"]
                    == "https://api.company.com/authorize"
                )
                assert (
                    data["registration_endpoint"] == "https://api.company.com/register"
                )
