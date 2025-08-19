"""WorkOS authentication providers for FastMCP.

This module provides two WorkOS authentication strategies:

1. WorkOSProvider - OAuth proxy for WorkOS SSO (non-DCR)
2. AuthKitProvider - DCR-compliant provider for WorkOS AuthKit

Choose based on your WorkOS setup and authentication requirements.
"""

from __future__ import annotations

import httpx
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.responses import JSONResponse
from starlette.routing import Route

from fastmcp.server.auth import AccessToken, RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.proxy import OAuthProxy
from fastmcp.server.auth.registry import register_provider
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.types import NotSet, NotSetT

logger = get_logger(__name__)


class WorkOSProviderSettings(BaseSettings):
    """Settings for WorkOS OAuth provider."""

    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_SERVER_AUTH_WORKOS_",
        env_file=".env",
        extra="ignore",
    )

    client_id: str | None = None
    client_secret: SecretStr | None = None
    base_url: AnyHttpUrl | str | None = None
    redirect_path: str | None = None
    organization_id: str | None = None
    connection_id: str | None = None
    required_scopes: list[str] | None = None
    timeout_seconds: int | None = None


class WorkOSTokenVerifier(TokenVerifier):
    """Token verifier for WorkOS OAuth tokens.

    WorkOS tokens are opaque, so we verify them by calling
    WorkOS's API to check validity and get user info.
    """

    def __init__(
        self,
        *,
        client_secret: str,
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
    ):
        """Initialize the WorkOS token verifier.

        Args:
            client_secret: WorkOS client secret (used as API key)
            required_scopes: Required OAuth scopes
            timeout_seconds: HTTP request timeout
        """
        super().__init__(required_scopes=required_scopes)
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify WorkOS OAuth token by calling WorkOS API."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Use WorkOS User Management API to validate token
                response = await client.get(
                    "https://api.workos.com/user_management/users/me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "FastMCP-WorkOS-OAuth",
                    },
                )

                if response.status_code != 200:
                    logger.debug(
                        "WorkOS token verification failed: %d - %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return None

                user_data = response.json()

                # Create AccessToken with WorkOS user info
                return AccessToken(
                    token=token,
                    client_id=str(user_data.get("id", "unknown")),
                    scopes=self.required_scopes or [],
                    expires_at=None,  # WorkOS tokens don't typically expire
                    claims={
                        "sub": user_data.get("id"),
                        "email": user_data.get("email"),
                        "first_name": user_data.get("first_name"),
                        "last_name": user_data.get("last_name"),
                        "profile_picture_url": user_data.get("profile_picture_url"),
                        "organization_id": user_data.get("organization_id"),
                    },
                )

        except httpx.RequestError as e:
            logger.debug("Failed to verify WorkOS token: %s", e)
            return None
        except Exception as e:
            logger.debug("WorkOS token verification error: %s", e)
            return None


@register_provider("WORKOS")
class WorkOSProvider(OAuthProxy):
    """Complete WorkOS OAuth provider for FastMCP.

    This provider implements WorkOS SSO integration using the OAuth Proxy pattern.
    It's designed for traditional WorkOS SSO setups that don't support Dynamic
    Client Registration (DCR).

    IMPORTANT: WorkOS SSO requires EITHER organization_id OR connection_id to be set.
    Without one of these, authentication will fail with "invalid-connection-selector".

    Features:
    - Transparent OAuth proxy to WorkOS
    - Automatic token validation via WorkOS API
    - User information extraction
    - Support for SSO connections and organizations

    Setup Requirements:
    1. Create a WorkOS application in your dashboard
    2. Configure redirect URI as: http://localhost:8000/auth/callback
    3. Note your Client ID and Client Secret
    4. Set either organization_id OR connection_id for SSO

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.workos import WorkOSProvider

        auth = WorkOSProvider(
            client_id="client_123",
            client_secret="sk_test_456",
            base_url="http://localhost:8000",
            organization_id="org_123"  # Optional for SSO
        )

        mcp = FastMCP("My App", auth=auth)
        ```
    """

    def __init__(
        self,
        *,
        client_id: str | NotSetT = NotSet,
        client_secret: str | NotSetT = NotSet,
        base_url: AnyHttpUrl | str | NotSetT = NotSet,
        redirect_path: str | NotSetT = NotSet,
        organization_id: str | None | NotSetT = NotSet,
        connection_id: str | None | NotSetT = NotSet,
        required_scopes: list[str] | None | NotSetT = NotSet,
        timeout_seconds: int | NotSetT = NotSet,
    ):
        """Initialize WorkOS OAuth provider.

        Args:
            client_id: WorkOS client ID
            client_secret: WorkOS client secret
            base_url: Public URL of your FastMCP server (for OAuth callbacks)
            redirect_path: Redirect path configured in WorkOS (defaults to "/auth/callback")
            organization_id: Optional WorkOS organization ID for SSO
            connection_id: Optional WorkOS connection ID for SSO
            required_scopes: Required scopes
            timeout_seconds: HTTP request timeout for WorkOS API calls
        """
        settings = WorkOSProviderSettings.model_validate(
            {
                k: v
                for k, v in {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "base_url": base_url,
                    "redirect_path": redirect_path,
                    "organization_id": organization_id,
                    "connection_id": connection_id,
                    "required_scopes": required_scopes,
                    "timeout_seconds": timeout_seconds,
                }.items()
                if v is not NotSet
            }
        )

        # Validate required settings
        if not settings.client_id:
            raise ValueError(
                "client_id is required - set via parameter or FASTMCP_SERVER_AUTH_WORKOS_CLIENT_ID"
            )
        if not settings.client_secret:
            raise ValueError(
                "client_secret is required - set via parameter or FASTMCP_SERVER_AUTH_WORKOS_CLIENT_SECRET"
            )

        # WorkOS SSO requires either organization_id or connection_id
        if not settings.organization_id and not settings.connection_id:
            raise ValueError(
                "WorkOS SSO requires either organization_id or connection_id. "
                "Set FASTMCP_SERVER_AUTH_WORKOS_ORGANIZATION_ID or FASTMCP_SERVER_AUTH_WORKOS_CONNECTION_ID"
            )

        # Apply defaults
        base_url_final = settings.base_url or "http://localhost:8000"
        redirect_path_final = settings.redirect_path or "/auth/callback"
        timeout_seconds_final = settings.timeout_seconds or 10

        # Extract secret string from SecretStr
        client_secret_str = (
            settings.client_secret.get_secret_value() if settings.client_secret else ""
        )

        # Create WorkOS token verifier
        token_verifier = WorkOSTokenVerifier(
            client_secret=client_secret_str,
            required_scopes=settings.required_scopes,
            timeout_seconds=timeout_seconds_final,
        )

        # WorkOS SSO requires either organization or connection parameter
        # We'll pass these as additional parameters that get forwarded with each auth request
        self.organization_id = settings.organization_id
        self.connection_id = settings.connection_id

        # Initialize OAuth proxy with WorkOS endpoints
        super().__init__(
            upstream_authorization_endpoint="https://api.workos.com/sso/authorize",
            upstream_token_endpoint="https://api.workos.com/sso/token",
            upstream_client_id=settings.client_id,
            upstream_client_secret=client_secret_str,
            token_verifier=token_verifier,
            base_url=base_url_final,
            redirect_path=redirect_path_final,
            issuer_url=base_url_final,
        )

        logger.info(
            "Initialized WorkOS OAuth provider for client %s",
            settings.client_id,
        )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Handle authorization request with WorkOS-specific parameters.

        WorkOS requires either organization or connection parameter for SSO.
        """
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        # Get the base authorization URL from parent
        redirect_url = await super().authorize(client, params)

        # Parse the URL to add WorkOS-specific parameters
        parsed = urlparse(redirect_url)
        query_params = parse_qs(parsed.query)

        # Add WorkOS SSO parameters if configured
        if self.organization_id:
            query_params["organization"] = [self.organization_id]
        elif self.connection_id:
            query_params["connection"] = [self.connection_id]

        # Rebuild the URL with the additional parameters
        new_query = urlencode(query_params, doseq=True)
        modified_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            )
        )

        return modified_url


class AuthKitProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_SERVER_AUTH_AUTHKITPROVIDER_",
        env_file=".env",
        extra="ignore",
    )

    authkit_domain: AnyHttpUrl
    base_url: AnyHttpUrl
    required_scopes: list[str] | None = None


@register_provider("AUTHKIT")
class AuthKitProvider(RemoteAuthProvider):
    """AuthKit metadata provider for DCR (Dynamic Client Registration).

    This provider implements AuthKit integration using metadata forwarding
    instead of OAuth proxying. This is the recommended approach for WorkOS DCR
    as it allows WorkOS to handle the OAuth flow directly while FastMCP acts
    as a resource server.

    IMPORTANT SETUP REQUIREMENTS:

    1. Enable Dynamic Client Registration in WorkOS Dashboard:
       - Go to Applications → Configuration
       - Toggle "Dynamic Client Registration" to enabled

    2. Configure your FastMCP server URL as a callback:
       - Add your server URL to the Redirects tab in WorkOS dashboard
       - Example: https://your-fastmcp-server.com/oauth2/callback

    For detailed setup instructions, see:
    https://workos.com/docs/authkit/mcp/integrating/token-verification

    Example:
        ```python
        from fastmcp.server.auth.providers.workos import AuthKitProvider

        # Create AuthKit metadata provider (JWT verifier created automatically)
        workos_auth = AuthKitProvider(
            authkit_domain="https://your-workos-domain.authkit.app",
            base_url="https://your-fastmcp-server.com",
        )

        # Use with FastMCP
        mcp = FastMCP("My App", auth=workos_auth)
        ```
    """

    def __init__(
        self,
        *,
        authkit_domain: AnyHttpUrl | str | NotSetT = NotSet,
        base_url: AnyHttpUrl | str | NotSetT = NotSet,
        required_scopes: list[str] | None | NotSetT = NotSet,
        token_verifier: TokenVerifier | None = None,
    ):
        """Initialize AuthKit metadata provider.

        Args:
            authkit_domain: Your AuthKit domain (e.g., "https://your-app.authkit.app")
            base_url: Public URL of this FastMCP server
            required_scopes: Optional list of scopes to require for all requests
            token_verifier: Optional token verifier. If None, creates JWT verifier for AuthKit
        """
        settings = AuthKitProviderSettings.model_validate(
            {
                k: v
                for k, v in {
                    "authkit_domain": authkit_domain,
                    "base_url": base_url,
                    "required_scopes": required_scopes,
                }.items()
                if v is not NotSet
            }
        )

        self.authkit_domain = str(settings.authkit_domain).rstrip("/")
        self.base_url = str(settings.base_url).rstrip("/")

        # Create default JWT verifier if none provided
        if token_verifier is None:
            token_verifier = JWTVerifier(
                jwks_uri=f"{self.authkit_domain}/oauth2/jwks",
                issuer=self.authkit_domain,
                algorithm="RS256",
                required_scopes=settings.required_scopes,
            )

        # Initialize RemoteAuthProvider with AuthKit as the authorization server
        super().__init__(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl(self.authkit_domain)],
            resource_server_url=self.base_url,
        )

    def get_routes(self) -> list[Route]:
        """Get OAuth routes including AuthKit authorization server metadata forwarding.

        This returns the standard protected resource routes plus an authorization server
        metadata endpoint that forwards AuthKit's OAuth metadata to clients.
        """
        # Get the standard protected resource routes from RemoteAuthProvider
        routes = super().get_routes()

        async def oauth_authorization_server_metadata(request):
            """Forward AuthKit OAuth authorization server metadata with FastMCP customizations."""
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.authkit_domain}/.well-known/oauth-authorization-server"
                    )
                    response.raise_for_status()
                    metadata = response.json()
                    return JSONResponse(metadata)
            except Exception as e:
                return JSONResponse(
                    {
                        "error": "server_error",
                        "error_description": f"Failed to fetch AuthKit metadata: {e}",
                    },
                    status_code=500,
                )

        # Add AuthKit authorization server metadata forwarding
        routes.append(
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=oauth_authorization_server_metadata,
                methods=["GET"],
            )
        )

        return routes
