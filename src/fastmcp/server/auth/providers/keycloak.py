"""Keycloak authentication provider for FastMCP.

This module provides KeycloakAuthProvider - a complete authentication solution that integrates
with Keycloak's OAuth 2.1 and OpenID Connect services, supporting Dynamic Client Registration (DCR)
for seamless MCP client authentication.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.responses import JSONResponse, RedirectResponse
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
        required_scopes: list[str] | None | NotSetT = NotSet,
        token_verifier: TokenVerifier | None = None,
    ):
        """Initialize Keycloak metadata provider.

        Args:
            realm_url: Your Keycloak realm URL (e.g., "https://keycloak.example.com/realms/myrealm")
            base_url: Public URL of this FastMCP server
            required_scopes: Optional list of scopes to require for all requests
            token_verifier: Optional token verifier. If None, creates JWT verifier for Keycloak
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

        base_url = str(settings.base_url).rstrip("/")
        self.realm_url = str(settings.realm_url).rstrip("/")

        # Discover OIDC configuration from Keycloak
        self.oidc_config = self._discover_oidc_configuration()

        # Create default JWT verifier if none provided
        if token_verifier is None:
            # After discovery, jwks_uri and issuer are guaranteed non-None (defaults applied)
            token_verifier = JWTVerifier(
                jwks_uri=str(self.oidc_config.jwks_uri),
                issuer=str(self.oidc_config.issuer),
                algorithm="RS256",
                required_scopes=settings.required_scopes,
                audience=None,  # Allow any audience for dynamic client registration
            )
        elif settings.required_scopes is not None:
            # Merge provider-level required scopes into custom verifier
            existing_scopes = list(token_verifier.required_scopes or [])
            for scope in settings.required_scopes:
                if scope not in existing_scopes:
                    existing_scopes.append(scope)
            token_verifier.required_scopes = existing_scopes

        # Initialize RemoteAuthProvider with FastMCP as the authorization server proxy
        super().__init__(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl(base_url)],
            base_url=base_url,
        )

    def _discover_oidc_configuration(self) -> OIDCConfiguration:
        """Discover OIDC configuration from Keycloak with default value handling."""
        # Fetch original OIDC configuration from Keycloak
        config_url = AnyHttpUrl(f"{self.realm_url}/.well-known/openid-configuration")
        config = OIDCConfiguration.get_oidc_configuration(
            config_url, strict=False, timeout_seconds=10
        )

        # Apply default values for fields that might be missing
        if not config.jwks_uri:
            config.jwks_uri = f"{self.realm_url}/.well-known/jwks.json"
        if not config.issuer:
            config.issuer = self.realm_url
        if not config.registration_endpoint:
            config.registration_endpoint = (
                f"{self.realm_url}/clients-registrations/openid-connect"
            )
        if not config.authorization_endpoint:
            config.authorization_endpoint = (
                f"{self.realm_url}/protocol/openid-connect/auth"
            )

        return config

    def get_routes(
        self,
        mcp_path: str | None = None,
    ) -> list[Route]:
        """Get OAuth routes including authorization server metadata endpoint.

        This returns the standard protected resource routes plus an authorization server
        metadata endpoint that allows OAuth clients to discover and participate in auth flows
        with this MCP server acting as a proxy to Keycloak.

        The proxy is necessary to:
        - Inject server-configured required scopes into client registration requests
        - Modify client registration responses for FastMCP compatibility
        - Inject server-configured required scopes into authorization requests
        - Prevent CORS issues when FastMCP and Keycloak are on different origins

        Args:
            mcp_path: The path where the MCP endpoint is mounted (e.g., "/mcp")
        """
        # Get the standard protected resource routes from RemoteAuthProvider
        routes = super().get_routes(mcp_path)

        async def oauth_authorization_server_metadata(request):
            """Return OAuth authorization server metadata for this FastMCP authorization server proxy."""
            logger.debug("OAuth authorization server metadata endpoint called")

            # Create a copy of Keycloak OAuth metadata as starting point for the
            # OAuth metadata of this FastMCP authorization server proxy
            config = self.oidc_config.model_copy()

            # Add/modify registration and authorization endpoints to intercept
            # Dynamic Client Registration (DCR) requests on this FastMCP authorization server proxy
            base_url = str(self.base_url).rstrip("/")
            config.registration_endpoint = f"{base_url}/register"
            config.authorization_endpoint = f"{base_url}/authorize"

            # Return the OAuth metadata of this FastMCP authorization server proxy as JSON
            metadata = config.model_dump(by_alias=True, exclude_none=True)
            return JSONResponse(metadata)

        # Add authorization server metadata discovery endpoint
        routes.append(
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=oauth_authorization_server_metadata,
                methods=["GET"],
            )
        )

        async def register_client_proxy(request):
            """Proxy client registration to Keycloak with request and response modifications.

            This proxy modifies both the client registration request and response to ensure FastMCP
            compatibility:

            Request modifications:
            - Injects server-configured required scopes into the registration request to ensure the client
              is granted the necessary scopes for token validation

            Response modifications:
            - Changes token_endpoint_auth_method from 'client_secret_basic' to 'client_secret_post'
            - Filters response_types to only include 'code' (removes 'none' and others)

            These modifications cannot be easily achieved through Keycloak server configuration
            alone because:
            - Scope assignment for dynamic clients can not be achieved the static configuration but
              requires runtime injection
            - Keycloak's default authentication flows advertise 'client_secret_basic' as token endpoint
              authentication method globally and client-specific overrides would require pre-registration
              or complex policies
            - Response type filtering would require custom Keycloak extensions
            """
            logger.debug("Client registration proxy endpoint called")
            try:
                # Get and parse the request body to retrieve client registration data
                body = await request.body()
                registration_data = json.loads(body)
                logger.info(
                    f"Intercepting client registration request - redirect_uris: {registration_data.get('redirect_uris')}, scope: {registration_data.get('scope') or 'N/A'}"
                )

                # Add the server's required scopes to the client registration data
                if self.token_verifier.required_scopes:
                    scopes = parse_scopes(registration_data.get("scope")) or []
                    merged_scopes = scopes + [
                        scope
                        for scope in self.token_verifier.required_scopes
                        if scope not in scopes
                    ]
                    logger.info(
                        f"Merging server-configured required scopes with client-requested scopes: {merged_scopes}"
                    )
                    registration_data["scope"] = " ".join(merged_scopes)
                    # Update the body with modified client registration data
                    body = json.dumps(registration_data).encode("utf-8")

                # Forward the registration request to Keycloak
                async with httpx.AsyncClient(timeout=10.0) as client:
                    logger.info(
                        f"Forwarding client registration to Keycloak: {self.oidc_config.registration_endpoint}"
                    )
                    # Forward all headers except Host and hop-by-hop headers
                    # Exclude Content-Length so httpx can recompute it for the modified body
                    forward_headers = {
                        key: value
                        for key, value in request.headers.items()
                        if key.lower()
                        not in {"host", "content-length", "transfer-encoding"}
                    }
                    # Ensure Content-Type is set correctly for our JSON body
                    forward_headers["Content-Type"] = "application/json"

                    response = await client.post(
                        str(self.oidc_config.registration_endpoint),
                        content=body,
                        headers=forward_headers,
                    )

                    if response.status_code != 201:
                        error_detail = {"error": "registration_failed"}
                        try:
                            if response.headers.get("content-type", "").startswith(
                                "application/json"
                            ):
                                error_detail = response.json()
                            else:
                                error_detail = {
                                    "error": "registration_failed",
                                    "error_description": response.text[:500]
                                    if response.text
                                    else f"HTTP {response.status_code}",
                                }
                        except Exception:
                            error_detail = {
                                "error": "registration_failed",
                                "error_description": f"HTTP {response.status_code}",
                            }

                        return JSONResponse(
                            error_detail,
                            status_code=response.status_code,
                        )

                    # Modify the response to be compatible with FastMCP
                    logger.info(
                        "Modifying 'token_endpoint_auth_method' and 'response_types' in client info for FastMCP compatibility"
                    )
                    client_info = response.json()

                    logger.debug(
                        f"Original client info from Keycloak: token_endpoint_auth_method={client_info.get('token_endpoint_auth_method')}, response_types={client_info.get('response_types')}, redirect_uris={client_info.get('redirect_uris')}"
                    )

                    # Fix token_endpoint_auth_method
                    client_info["token_endpoint_auth_method"] = "client_secret_post"

                    # Fix response_types - ensure only "code"
                    if "response_types" in client_info:
                        client_info["response_types"] = ["code"]

                    logger.debug(
                        f"Modified client info for FastMCP compatibility: token_endpoint_auth_method={client_info.get('token_endpoint_auth_method')}, response_types={client_info.get('response_types')}"
                    )

                    return JSONResponse(client_info, status_code=201)

            except Exception as e:
                return JSONResponse(
                    {
                        "error": "server_error",
                        "error_description": f"Client registration failed: {e}",
                    },
                    status_code=500,
                )

        # Add client registration proxy
        routes.append(
            Route(
                "/register",
                endpoint=register_client_proxy,
                methods=["POST"],
            )
        )

        async def authorize_proxy(request):
            """Proxy authorization requests to Keycloak with scope injection and CORS handling.

            This proxy is essential for scope management and CORS compatibility. It injects
            server-configured required scopes into authorization requests, ensuring that OAuth
            clients request the proper scopes even though they don't know what the server requires.
            Additionally, it prevents CORS issues when FastMCP and Keycloak are on different origins.

            The proxy ensures:
            - Injection of server-configured required scopes into the authorization request
            - Compatibility with OAuth clients that expect same-origin authorization flows by letting authorization
              requests stay on same origin as client registration requests
            """
            logger.debug("Authorization proxy endpoint called")
            try:
                logger.info(
                    f"Intercepting authorization request - query_params: {request.query_params}"
                )

                # Add server-configured required scopes to the authorization request
                # Use multi_items() to preserve duplicate query parameters (e.g., multiple 'resource' per RFC 8707)
                query_items = list(request.query_params.multi_items())
                if self.token_verifier.required_scopes:
                    existing_scopes = (
                        parse_scopes(request.query_params.get("scope")) or []
                    )
                    missing_scopes = [
                        scope
                        for scope in self.token_verifier.required_scopes
                        if scope not in existing_scopes
                    ]
                    if missing_scopes:
                        logger.info(
                            f"Adding server-configured required scopes to authorization request: {missing_scopes}"
                        )
                        scope_value = " ".join(existing_scopes + missing_scopes)
                        # Remove existing scope parameter and add the updated one
                        query_items = [(k, v) for k, v in query_items if k != "scope"]
                        query_items.append(("scope", scope_value))

                # Build authorization request URL for redirecting to Keycloak and including the (potentially modified) query string
                authorization_url = str(self.oidc_config.authorization_endpoint)
                query_string = urlencode(query_items)
                if query_string:
                    authorization_url += f"?{query_string}"

                # Redirect authorization request to Keycloak's authorization endpoint
                logger.info(
                    f"Redirecting authorization request to Keycloak: {authorization_url}"
                )
                return RedirectResponse(url=authorization_url, status_code=302)

            except Exception as e:
                return JSONResponse(
                    {
                        "error": "server_error",
                        "error_description": f"Authorization request failed: {e}",
                    },
                    status_code=500,
                )

        # Add authorization endpoint proxy
        routes.append(
            Route(
                "/authorize",
                endpoint=authorize_proxy,
                methods=["GET"],
            )
        )

        return routes
