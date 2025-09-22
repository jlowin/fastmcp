"""Azure (Microsoft Entra) OAuth provider for FastMCP.

This provider implements Azure/Microsoft Entra ID OAuth authentication
using the OAuth Proxy pattern for non-DCR OAuth flows.
"""

from __future__ import annotations

import httpx
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.utilities.auth import parse_scopes
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.types import NotSet, NotSetT

logger = get_logger(__name__)


class AzureProviderSettings(BaseSettings):
    """Settings for Azure OAuth provider."""

    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_SERVER_AUTH_AZURE_",
        env_file=".env",
        extra="ignore",
    )

    client_id: str | None = None
    client_secret: SecretStr | None = None
    tenant_id: str | None = None
    audience: str | None = None
    api_client_id: str | None = None
    base_url: str | None = None
    redirect_path: str | None = None
    required_scopes: list[str] | None = None
    timeout_seconds: int | None = None
    allowed_client_redirect_uris: list[str] | None = None

    @field_validator("required_scopes", mode="before")
    @classmethod
    def _parse_scopes(cls, v):
        return parse_scopes(v)


class AzureTokenVerifier(TokenVerifier):
    """Token verifier for Azure OAuth tokens.

    Azure tokens are JWTs, but we verify them by calling the Microsoft Graph API
    to get user information and validate the token.
    """

    def __init__(
        self,
        *,
        required_scopes: list[str] | None = None,
        timeout_seconds: int = 10,
    ):
        """Initialize the Azure token verifier.

        Args:
            required_scopes: Required OAuth scopes
            timeout_seconds: HTTP request timeout
        """
        super().__init__(required_scopes=required_scopes)
        self.timeout_seconds = timeout_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify Azure OAuth token by calling Microsoft Graph API."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Use Microsoft Graph API to validate token and get user info
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": "FastMCP-Azure-OAuth",
                    },
                )

                if response.status_code != 200:
                    logger.debug(
                        "Azure token verification failed: %d - %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return None

                user_data = response.json()

                # Create AccessToken with Azure user info
                return AccessToken(
                    token=token,
                    client_id=str(user_data.get("id", "unknown")),
                    scopes=self.required_scopes or [],
                    expires_at=None,
                    claims={
                        "sub": user_data.get("id"),
                        "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                        "name": user_data.get("displayName"),
                        "given_name": user_data.get("givenName"),
                        "family_name": user_data.get("surname"),
                        "job_title": user_data.get("jobTitle"),
                        "office_location": user_data.get("officeLocation"),
                    },
                )

        except httpx.RequestError as e:
            logger.debug("Failed to verify Azure token: %s", e)
            return None
        except Exception as e:
            logger.debug("Azure token verification error: %s", e)
            return None


class AzureProvider(OAuthProxy):
    """Azure (Microsoft Entra) OAuth provider for FastMCP.

    This provider implements Azure/Microsoft Entra ID authentication using the
    OAuth Proxy pattern. It supports both organizational accounts and personal
    Microsoft accounts depending on the tenant configuration.

    Features:
    - Transparent OAuth proxy to Azure/Microsoft identity platform
    - Automatic token validation via Microsoft Graph API or JWT verification
    - User information extraction
    - Support for different tenant configurations (common, organizations, consumers)
    - Support for custom API audiences with proper JWT validation

    Setup Requirements:
    1. Register an application in Azure Portal (portal.azure.com)
    2. Configure redirect URI as: http://localhost:8000/auth/callback
    3. Note your Application (client) ID and create a client secret
    4. Optionally note your Directory (tenant) ID for single-tenant apps
    5. For custom APIs, configure your API's Application ID URI as the audience

    Example with Microsoft Graph (default):
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.azure import AzureProvider

        auth = AzureProvider(
            client_id="your-client-id",
            client_secret="your-client-secret",
            tenant_id="your-tenant-id",
            base_url="http://localhost:8000"
        )

        mcp = FastMCP("My App", auth=auth)
        ```

    Example with custom API audience:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.azure import AzureProvider

        auth = AzureProvider(
            client_id="your-client-id",
            client_secret="your-client-secret",
            tenant_id="your-tenant-id",
            audience="api://your-api-id",  # Your API's Application ID URI
            api_client_id="your-api-client-id",  # Your API's Client ID
            required_scopes=["your_api_scope"],
        )

        mcp = FastMCP("My App", auth=auth)
        ```
    """

    def __init__(
        self,
        *,
        client_id: str | NotSetT = NotSet,
        client_secret: str | NotSetT = NotSet,
        tenant_id: str | NotSetT = NotSet,
        audience: str | None | NotSetT = NotSet,
        api_client_id: str | None | NotSetT = NotSet,
        base_url: str | NotSetT = NotSet,
        redirect_path: str | NotSetT = NotSet,
        required_scopes: list[str] | None | NotSetT = NotSet,
        timeout_seconds: int | NotSetT = NotSet,
        allowed_client_redirect_uris: list[str] | NotSetT = NotSet,
    ):
        """Initialize Azure OAuth provider.

        Args:
            client_id: Azure application (client) ID
            client_secret: Azure client secret
            tenant_id: Azure tenant ID (your specific tenant ID, "organizations", or "consumers")
            audience: Optional audience/resource for the token. For custom APIs, use your API's
                     Application ID URI (e.g., "api://your-api-id"). If not specified, defaults
                     to Microsoft Graph. The audience determines which API the token can access.
            api_client_id: The actual client ID (GUID) of your API application. Required when
                          audience is specified, as Azure AD v2.0 tokens use this as the 'aud' claim.
            base_url: Public URL of your FastMCP server (for OAuth callbacks)
            redirect_path: Redirect path configured in Azure (defaults to "/auth/callback")
            required_scopes: Required scopes. When audience is specified, use your API's scopes without the audience prefix.
                           Defaults to ["User.Read", "email", "openid", "profile"] for Graph API.
            timeout_seconds: HTTP request timeout for Azure API calls
            allowed_client_redirect_uris: List of allowed redirect URI patterns for MCP clients.
                If None (default), all URIs are allowed. If empty list, no URIs are allowed.
        """
        settings = AzureProviderSettings.model_validate(
            {
                k: v
                for k, v in {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "tenant_id": tenant_id,
                    "audience": audience,
                    "api_client_id": api_client_id,
                    "base_url": base_url,
                    "redirect_path": redirect_path,
                    "required_scopes": required_scopes,
                    "timeout_seconds": timeout_seconds,
                    "allowed_client_redirect_uris": allowed_client_redirect_uris,
                }.items()
                if v is not NotSet
            }
        )

        # Validate required settings
        if not settings.client_id:
            raise ValueError("client_id is required - set via parameter or FASTMCP_SERVER_AUTH_AZURE_CLIENT_ID")
        if not settings.client_secret:
            raise ValueError("client_secret is required - set via parameter or FASTMCP_SERVER_AUTH_AZURE_CLIENT_SECRET")

        # Validate tenant_id is provided
        if not settings.tenant_id:
            raise ValueError(
                "tenant_id is required - set via parameter or FASTMCP_SERVER_AUTH_AZURE_TENANT_ID. "
                "Use your Azure tenant ID (found in Azure Portal), 'organizations', or 'consumers'"
            )
        # Validate that api_client_id is provided when audience is specified
        if settings.audience and not settings.api_client_id:
            raise ValueError(
                "api_client_id is required when audience is specified. "
                "This should be the actual client ID (GUID) of your API application, "
                "not the Application ID URI."
            )
        # Validate that required_scopes is provided when audience is specified
        if settings.audience and not settings.required_scopes:
            raise ValueError("required_scopes is required when audience is specified")
        if settings.audience and not isinstance(settings.required_scopes, list):
            raise ValueError("required_scopes must be a list when audience is specified")
        # Validate that scopes does not have audience as prefix when audience is specified
        if (
            settings.audience
            and isinstance(settings.required_scopes, list)
            and any(scope.startswith(f"{settings.audience}/") for scope in settings.required_scopes)
        ):
            raise ValueError("Scopes in required_scopes must not be prefixed with audience. ")

        # Apply defaults
        self.audience = settings.audience
        tenant_id_final = settings.tenant_id
        timeout_seconds_final = settings.timeout_seconds or 10
        allowed_client_redirect_uris_final = settings.allowed_client_redirect_uris

        # Handle audience and scopes
        api_client_id_final = settings.api_client_id

        # Create appropriate token verifier based on audience
        if self.audience:
            logger.debug(
                "Using custom audience: %s - tokens will be verified using JWT validation",
                self.audience,
            )

            issuer = f"https://login.microsoftonline.com/{tenant_id_final}/v2.0"
            jwks_uri = f"https://login.microsoftonline.com/{tenant_id_final}/discovery/v2.0/keys"

            scopes_final = settings.required_scopes

            token_verifier = JWTVerifier(
                jwks_uri=jwks_uri,
                issuer=issuer,
                audience=api_client_id_final,
                algorithm="RS256",
                required_scopes=scopes_final,
            )

        else:
            # No audience specified - use Microsoft Graph verification
            logger.debug("Using Microsoft Graph API as default audience")

            scopes_final = settings.required_scopes or [
                "User.Read",
                "email",
                "openid",
                "profile",
            ]

            # Create Graph API verifier (using existing AzureTokenVerifier class)
            token_verifier = AzureTokenVerifier(
                required_scopes=scopes_final,
                timeout_seconds=timeout_seconds_final,
            )

        # Extract secret string from SecretStr
        client_secret_str = settings.client_secret.get_secret_value() if settings.client_secret else ""

        # Build Azure OAuth endpoints with tenant
        authorization_endpoint = f"https://login.microsoftonline.com/{tenant_id_final}/oauth2/v2.0/authorize"
        token_endpoint = f"https://login.microsoftonline.com/{tenant_id_final}/oauth2/v2.0/token"

        # Initialize OAuth proxy with Azure endpoints
        super().__init__(
            upstream_authorization_endpoint=authorization_endpoint,
            upstream_token_endpoint=token_endpoint,
            upstream_client_id=settings.client_id,
            upstream_client_secret=client_secret_str,
            token_verifier=token_verifier,
            base_url=settings.base_url,
            redirect_path=settings.redirect_path,
            issuer_url=settings.base_url,
            allowed_client_redirect_uris=allowed_client_redirect_uris_final,
        )

        logger.info(
            "Initialized Azure OAuth provider for client %s with tenant %s%s",
            settings.client_id,
            tenant_id_final,
            f" and audience {self.audience}" if self.audience else "",
        )

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Start OAuth transaction and redirect to Azure AD.

        Override parent's authorize method to filter out the 'resource' parameter
        which is not supported by Azure AD v2.0 endpoints. The v2.0 endpoints use
        scopes to determine the resource/audience instead of a separate parameter.

        Args:
            client: OAuth client information
            params: Authorization parameters from the client

        Returns:
            Authorization URL to redirect the user to Azure AD
        """
        # Clear the resource parameter that Azure AD v2.0 doesn't support
        # This parameter comes from RFC 8707 (OAuth 2.0 Resource Indicators)
        # but Azure AD v2.0 uses scopes instead to determine the audience
        params_to_use = params
        if hasattr(params, "resource"):
            original_resource = getattr(params, "resource", None)
            if original_resource is not None:
                params_to_use = params.model_copy(update={"resource": None})
                if original_resource:
                    logger.debug(
                        "Filtering out 'resource' parameter '%s' for Azure AD v2.0 (use scopes instead)",
                        original_resource,
                    )
        original_scopes = params_to_use.scopes or self.required_scopes
        prefixed_scopes = self._add_prefix_to_scopes(original_scopes)

        # Create modified params with prefixed scopes
        modified_params = params_to_use.model_copy(update={"scopes": prefixed_scopes})

        return await super().authorize(client, modified_params)

    def _add_prefix_to_scopes(self, scopes: list[str]) -> list[str]:
        """Add API URI prefix for authorization request."""
        prefixed = []
        for scope in scopes:
            if scope in ["openid", "profile", "email", "offline_access"]:
                prefixed.append(scope)
            else:
                prefixed.append(f"{self.audience}/{scope}")

        # Always include openid for Entra ID
        if "openid" not in prefixed:
            prefixed.insert(0, "openid")

        return prefixed
