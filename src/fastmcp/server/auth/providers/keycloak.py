"""Keycloak authentication provider for FastMCP.

This module provides KeycloakAuthProvider - a complete authentication solution that integrates
with Keycloak's OAuth 2.1 and OpenID Connect services, supporting Dynamic Client Registration (DCR)
for seamless MCP client authentication.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.responses import JSONResponse
from starlette.routing import Route

from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.utilities.auth import parse_scopes
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.types import NotSet, NotSetT

logger = get_logger(__name__)


class KeycloakProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_SERVER_AUTH_KEYCLOAK_",
        env_file=".env",
        extra="ignore",
    )

    realm_url: AnyHttpUrl
    base_url: AnyHttpUrl
    required_scopes: list[str] | None = None

    @field_validator("required_scopes", mode="before")
    @classmethod
    def _parse_scopes(cls, v):
        return parse_scopes(v)


class KeycloakAuthProvider(RemoteAuthProvider):
    """Keycloak metadata provider for DCR (Dynamic Client Registration).

    This provider implements Keycloak integration using metadata forwarding and
    dynamic endpoint discovery. This is the recommended approach for Keycloak DCR
    as it allows Keycloak to handle the OAuth flow directly while FastMCP acts
    as a resource server.

    IMPORTANT SETUP REQUIREMENTS:

    1. Enable Dynamic Client Registration in Keycloak Admin Console:
       - Go to Realm Settings → Client Registration
       - Enable "Anonymous" or "Authenticated" access for Dynamic Client Registration
       - Configure Client Registration Policies as needed

    2. Note your Realm URL:
       - Example: https://keycloak.example.com/realms/myrealm
       - This should be the full URL to your specific realm

    For detailed setup instructions, see:
    https://www.keycloak.org/securing-apps/client-registration

    Examples:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.keycloak import KeycloakAuthProvider

        # Method 1: Direct parameters
        keycloak_auth = KeycloakAuthProvider(
            realm_url="https://keycloak.example.com/realms/myrealm",
            base_url="https://your-fastmcp-server.com",
            required_scopes=["openid", "profile"],
        )

        # Method 2: Environment variables
        # Set: FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL=https://keycloak.example.com/realms/myrealm
        # Set: FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL=https://your-fastmcp-server.com
        # Set: FASTMCP_SERVER_AUTH_KEYCLOAK_REQUIRED_SCOPES=openid,profile
        keycloak_auth = KeycloakAuthProvider()

        # Method 3: Custom token verifier
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        custom_verifier = JWTVerifier(
            jwks_uri="https://keycloak.example.com/realms/myrealm/.well-known/jwks.json",
            issuer="https://keycloak.example.com/realms/myrealm",
            audience="my-client-id",
            required_scopes=["api:read", "api:write"]
        )

        keycloak_auth = KeycloakAuthProvider(
            realm_url="https://keycloak.example.com/realms/myrealm",
            base_url="https://your-fastmcp-server.com",
            token_verifier=custom_verifier,
        )

        # Use with FastMCP
        mcp = FastMCP("My App", auth=keycloak_auth)
        ```
    """

    def __init__(
        self,
        *,
        realm_url: AnyHttpUrl | str | NotSetT = NotSet,
        base_url: AnyHttpUrl | str | NotSetT = NotSet,
        token_verifier: TokenVerifier | None = None,
        required_scopes: list[str] | None | NotSetT = NotSet,
    ):
        """Initialize Keycloak metadata provider.

        Args:
            realm_url: Your Keycloak realm URL (e.g., "https://keycloak.example.com/realms/myrealm")
            base_url: Public URL of this FastMCP server
            token_verifier: Optional token verifier. If None, creates JWT verifier for Keycloak
            required_scopes: Optional list of scopes to require for all requests
        """
        settings = KeycloakProviderSettings.model_validate(
            {
                k: v
                for k, v in {
                    "realm_url": realm_url,
                    "base_url": base_url,
                    "required_scopes": required_scopes,
                }.items()
                if v is not NotSet
            }
        )

        self.realm_url = str(settings.realm_url).rstrip("/")
        self.base_url = str(settings.base_url).rstrip("/")

        # Discover endpoints from Keycloak OIDC configuration
        config_url = AnyHttpUrl(f"{self.realm_url}/.well-known/openid-configuration")
        self.oidc_config = OIDCConfiguration.get_oidc_configuration(
            config_url, strict=False, timeout_seconds=None
        )

        # Create default JWT verifier if none provided
        if token_verifier is None:
            jwks_uri = (
                str(self.oidc_config.jwks_uri)
                if self.oidc_config.jwks_uri
                else f"{self.realm_url}/.well-known/jwks.json"
            )
            issuer = (
                str(self.oidc_config.issuer)
                if self.oidc_config.issuer
                else self.realm_url
            )

            token_verifier = JWTVerifier(
                jwks_uri=jwks_uri,
                issuer=issuer,
                algorithm="RS256",
                required_scopes=settings.required_scopes,
            )

        # Initialize RemoteAuthProvider with Keycloak as the authorization server
        super().__init__(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl(self.realm_url)],
            base_url=self.base_url,
        )

    def get_routes(
        self,
        mcp_path: str | None = None,
        mcp_endpoint: Any | None = None,
    ) -> list[Route]:
        """Get OAuth routes including Keycloak authorization server metadata forwarding.

        This returns the standard protected resource routes plus an authorization server
        metadata endpoint that forwards Keycloak's OAuth metadata to clients.

        Args:
            mcp_path: The path where the MCP endpoint is mounted (e.g., "/mcp")
            mcp_endpoint: The MCP endpoint handler to protect with auth
        """
        # Get the standard protected resource routes from RemoteAuthProvider
        routes = super().get_routes(mcp_path, mcp_endpoint)

        async def oauth_authorization_server_metadata(request):
            """Forward Keycloak OAuth authorization server metadata with FastMCP customizations."""
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.realm_url}/.well-known/openid-configuration"
                    )
                    response.raise_for_status()
                    metadata = response.json()
                    return JSONResponse(metadata)
            except Exception as e:
                return JSONResponse(
                    {
                        "error": "server_error",
                        "error_description": f"Failed to fetch Keycloak metadata: {e}",
                    },
                    status_code=500,
                )

        # Add Keycloak authorization server metadata forwarding
        routes.append(
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=oauth_authorization_server_metadata,
                methods=["GET"],
            )
        )

        return routes
