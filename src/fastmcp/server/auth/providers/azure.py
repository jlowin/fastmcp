"""Azure (Microsoft Entra) OAuth provider for FastMCP.

This provider implements Azure/Microsoft Entra ID OAuth authentication
using the OAuth Proxy pattern for non-DCR OAuth flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from key_value.aio.protocols import AsyncKeyValue

from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.utilities.auth import parse_scopes
from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from mcp.server.auth.provider import AuthorizationParams
    from mcp.shared.auth import OAuthClientInformationFull

    try:
        from msal import ConfidentialClientApplication
    except ImportError:
        ConfidentialClientApplication = Any  # type: ignore[assignment, misc]

logger = get_logger(__name__)

# Standard OIDC scopes that should never be prefixed with identifier_uri.
# Per Microsoft docs: https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc
# "OIDC scopes are requested as simple string identifiers without resource prefixes"
OIDC_SCOPES = frozenset({"openid", "profile", "email", "offline_access"})


class AzureProvider(OAuthProxy):
    """Azure (Microsoft Entra) OAuth provider for FastMCP.

    This provider implements Azure/Microsoft Entra ID authentication using the
    OAuth Proxy pattern. It supports both organizational accounts and personal
    Microsoft accounts depending on the tenant configuration.

    Scope Handling:
    - required_scopes: Provide unprefixed scope names (e.g., ["read", "write"])
      → Automatically prefixed with identifier_uri during initialization
      → Validated on all tokens and advertised to MCP clients
    - additional_authorize_scopes: Provide full format (e.g., ["User.Read"])
      → NOT prefixed, NOT validated, NOT advertised to clients
      → Used to request Microsoft Graph or other upstream API permissions

    Features:
    - OAuth proxy to Azure/Microsoft identity platform
    - JWT validation using tenant issuer and JWKS
    - Supports tenant configurations: specific tenant ID, "organizations", or "consumers"
    - Custom API scopes and Microsoft Graph scopes in a single provider

    Setup:
    1. Create an App registration in Azure Portal
    2. Configure Web platform redirect URI: http://localhost:8000/auth/callback (or your custom path)
    3. Add an Application ID URI under "Expose an API" (defaults to api://{client_id})
    4. Add custom scopes (e.g., "read", "write") under "Expose an API"
    5. Set access token version to 2 in the App manifest: "requestedAccessTokenVersion": 2
    6. Create a client secret
    7. Get Application (client) ID, Directory (tenant) ID, and client secret

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.azure import AzureProvider

        # Standard Azure (Public Cloud)
        auth = AzureProvider(
            client_id="your-client-id",
            client_secret="your-client-secret",
            tenant_id="your-tenant-id",
            required_scopes=["read", "write"],  # Unprefixed scope names
            additional_authorize_scopes=["User.Read", "Mail.Read"],  # Optional Graph scopes
            base_url="http://localhost:8000",
            # identifier_uri defaults to api://{client_id}
        )

        # Azure Government
        auth_gov = AzureProvider(
            client_id="your-client-id",
            client_secret="your-client-secret",
            tenant_id="your-tenant-id",
            required_scopes=["read", "write"],
            base_authority="login.microsoftonline.us",  # Override for Azure Gov
            base_url="http://localhost:8000",
        )

        mcp = FastMCP("My App", auth=auth)
        ```
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        required_scopes: list[str],
        base_url: str,
        identifier_uri: str | None = None,
        issuer_url: str | None = None,
        redirect_path: str | None = None,
        additional_authorize_scopes: list[str] | None = None,
        allowed_client_redirect_uris: list[str] | None = None,
        client_storage: AsyncKeyValue | None = None,
        jwt_signing_key: str | bytes | None = None,
        require_authorization_consent: bool = True,
        base_authority: str = "login.microsoftonline.com",
    ) -> None:
        """Initialize Azure OAuth provider.

        Args:
            client_id: Azure application (client) ID from your App registration
            client_secret: Azure client secret from your App registration
            tenant_id: Azure tenant ID (specific tenant GUID, "organizations", or "consumers")
            identifier_uri: Optional Application ID URI for your custom API (defaults to api://{client_id}).
                This URI is automatically prefixed to all required_scopes during initialization.
                Example: identifier_uri="api://my-api" + required_scopes=["read"]
                → tokens validated for "api://my-api/read"
            base_url: Public URL where OAuth endpoints will be accessible (includes any mount path)
            issuer_url: Issuer URL for OAuth metadata (defaults to base_url). Use root-level URL
                to avoid 404s during discovery when mounting under a path.
            redirect_path: Redirect path configured in Azure App registration (defaults to "/auth/callback")
            base_authority: Azure authority base URL (defaults to "login.microsoftonline.com").
                For Azure Government, use "login.microsoftonline.us".
            required_scopes: Custom API scope names WITHOUT prefix (e.g., ["read", "write"]).
                - Automatically prefixed with identifier_uri during initialization
                - Validated on all tokens
                - Advertised in Protected Resource Metadata
                - Must match scope names defined in Azure Portal under "Expose an API"
                Example: ["read", "write"] → validates tokens containing ["api://xxx/read", "api://xxx/write"]
            additional_authorize_scopes: Microsoft Graph or other upstream scopes in full format.
                - NOT prefixed with identifier_uri
                - NOT validated on tokens
                - NOT advertised to MCP clients
                - Used to request additional permissions from Azure (e.g., Graph API access)
                Example: ["User.Read", "Mail.Read", "offline_access"]
                These scopes allow your FastMCP server to call Microsoft Graph APIs using the
                upstream Azure token, but MCP clients are unaware of them.
            allowed_client_redirect_uris: List of allowed redirect URI patterns for MCP clients.
                If None (default), all URIs are allowed. If empty list, no URIs are allowed.
            client_storage: Storage backend for OAuth state (client registrations, encrypted tokens).
                If None, a DiskStore will be created in the data directory (derived from `platformdirs`). The
                disk store will be encrypted using a key derived from the JWT Signing Key.
            jwt_signing_key: Secret for signing FastMCP JWT tokens (any string or bytes). If bytes are provided,
                they will be used as is. If a string is provided, it will be derived into a 32-byte key. If not
                provided, the upstream client secret will be used to derive a 32-byte key using PBKDF2.
            require_authorization_consent: Whether to require user consent before authorizing clients (default True).
                When True, users see a consent screen before being redirected to Azure.
                When False, authorization proceeds directly without user confirmation.
                SECURITY WARNING: Only disable for local development or testing environments.
        """
        # Parse scopes if provided as string
        parsed_required_scopes = parse_scopes(required_scopes)
        parsed_additional_scopes = (
            parse_scopes(additional_authorize_scopes)
            if additional_authorize_scopes
            else []
        )

        # Store Azure-specific config for get_msal_app()
        self._tenant_id = tenant_id
        self._base_authority = base_authority

        # Apply defaults
        self.identifier_uri = identifier_uri or f"api://{client_id}"
        self.additional_authorize_scopes = parsed_additional_scopes

        # Always validate tokens against the app's API client ID using JWT
        issuer = f"https://{base_authority}/{tenant_id}/v2.0"
        jwks_uri = f"https://{base_authority}/{tenant_id}/discovery/v2.0/keys"

        # Azure access tokens only include custom API scopes in the `scp` claim,
        # NOT standard OIDC scopes (openid, profile, email, offline_access).
        # Filter out OIDC scopes from validation - they'll still be sent to Azure
        # during authorization (handled by _prefix_scopes_for_azure).
        if parsed_required_scopes:
            validation_scopes = [
                s for s in parsed_required_scopes if s not in OIDC_SCOPES
            ]
            # If all scopes were OIDC scopes, use None (no scope validation)
            if not validation_scopes:
                validation_scopes = None
        else:
            validation_scopes = None

        token_verifier = JWTVerifier(
            jwks_uri=jwks_uri,
            issuer=issuer,
            audience=client_id,
            algorithm="RS256",
            required_scopes=validation_scopes,  # Only validate non-OIDC scopes
        )

        # Build Azure OAuth endpoints with tenant
        authorization_endpoint = (
            f"https://{base_authority}/{tenant_id}/oauth2/v2.0/authorize"
        )
        token_endpoint = f"https://{base_authority}/{tenant_id}/oauth2/v2.0/token"

        # Initialize OAuth proxy with Azure endpoints
        super().__init__(
            upstream_authorization_endpoint=authorization_endpoint,
            upstream_token_endpoint=token_endpoint,
            upstream_client_id=client_id,
            upstream_client_secret=client_secret,
            token_verifier=token_verifier,
            base_url=base_url,
            redirect_path=redirect_path,
            issuer_url=issuer_url or base_url,  # Default to base_url if not specified
            allowed_client_redirect_uris=allowed_client_redirect_uris,
            client_storage=client_storage,
            jwt_signing_key=jwt_signing_key,
            require_authorization_consent=require_authorization_consent,
            # Advertise full scopes including OIDC (even though we only validate non-OIDC)
            valid_scopes=parsed_required_scopes,
        )

        authority_info = ""
        if base_authority != "login.microsoftonline.com":
            authority_info = f" using authority {base_authority}"
        logger.info(
            "Initialized Azure OAuth provider for client %s with tenant %s%s%s",
            client_id,
            tenant_id,
            f" and identifier_uri {self.identifier_uri}" if self.identifier_uri else "",
            authority_info,
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
        # Don't modify the scopes in params - they stay unprefixed for MCP clients
        # We'll prefix them when building the Azure authorization URL (in _build_upstream_authorize_url)
        auth_url = await super().authorize(client, params_to_use)
        separator = "&" if "?" in auth_url else "?"
        return f"{auth_url}{separator}prompt=select_account"

    def _prefix_scopes_for_azure(self, scopes: list[str]) -> list[str]:
        """Prefix unprefixed custom API scopes with identifier_uri for Azure.

        This helper centralizes the scope prefixing logic used in both
        authorization and token refresh flows.

        Scopes that are NOT prefixed:
        - Standard OIDC scopes (openid, profile, email, offline_access)
        - Fully-qualified URIs (contain "://")
        - Scopes with path component (contain "/")

        Note: Microsoft Graph scopes (e.g., User.Read) should be passed via
        `additional_authorize_scopes` or use fully-qualified format
        (e.g., https://graph.microsoft.com/User.Read).

        Args:
            scopes: List of scopes, may be prefixed or unprefixed

        Returns:
            List of scopes with identifier_uri prefix applied where needed
        """
        prefixed = []
        for scope in scopes:
            if scope in OIDC_SCOPES:
                # Standard OIDC scopes - never prefix
                prefixed.append(scope)
            elif "://" in scope or "/" in scope:
                # Already fully-qualified (e.g., "api://xxx/read" or
                # "https://graph.microsoft.com/User.Read")
                prefixed.append(scope)
            else:
                # Unprefixed custom API scope - prefix with identifier_uri
                prefixed.append(f"{self.identifier_uri}/{scope}")
        return prefixed

    def _build_upstream_authorize_url(
        self, txn_id: str, transaction: dict[str, Any]
    ) -> str:
        """Build Azure authorization URL with prefixed scopes.

        Overrides parent to prefix scopes with identifier_uri before sending to Azure,
        while keeping unprefixed scopes in the transaction for MCP clients.
        """
        # Get unprefixed scopes from transaction
        unprefixed_scopes = transaction.get("scopes") or self.required_scopes or []

        # Prefix scopes for Azure authorization request
        prefixed_scopes = self._prefix_scopes_for_azure(unprefixed_scopes)

        # Add Microsoft Graph scopes (not validated, not prefixed)
        if self.additional_authorize_scopes:
            prefixed_scopes.extend(self.additional_authorize_scopes)

        # Temporarily modify transaction dict for parent's URL building
        modified_transaction = transaction.copy()
        modified_transaction["scopes"] = prefixed_scopes

        # Let parent build the URL with prefixed scopes
        return super()._build_upstream_authorize_url(txn_id, modified_transaction)

    def _prepare_scopes_for_upstream_refresh(self, scopes: list[str]) -> list[str]:
        """Prepare scopes for Azure token refresh.

        Azure requires:
        1. Fully-qualified custom scopes (e.g., "api://xxx/read" not "read")
        2. Microsoft Graph scopes (e.g., "User.Read", "openid") sent as-is
        3. Additional scopes from provider config (additional_authorize_scopes)

        This method transforms base client scopes for Azure while keeping them
        unprefixed in storage to prevent accumulation.

        Args:
            scopes: Base scopes from RefreshToken (unprefixed, e.g., ["read"])

        Returns:
            Deduplicated list of scopes formatted for Azure token endpoint
        """
        logger.debug("Base scopes from storage: %s", scopes)

        # Filter out any additional_authorize_scopes that may have been stored
        # (they shouldn't be in storage, but clean them up if they are)
        additional_scopes_set = set(self.additional_authorize_scopes or [])
        base_scopes = [s for s in scopes if s not in additional_scopes_set]

        # Prefix base scopes with identifier_uri for Azure using shared helper
        prefixed_scopes = self._prefix_scopes_for_azure(base_scopes)

        # Add additional scopes (Graph + OIDC) for the Azure request
        # These are NOT stored in RefreshToken, only sent to Azure
        if self.additional_authorize_scopes:
            prefixed_scopes.extend(self.additional_authorize_scopes)

        # Deduplicate while preserving order (in case older tokens have duplicates)
        # Use dict.fromkeys() for O(n) deduplication with order preservation
        deduplicated_scopes = list(dict.fromkeys(prefixed_scopes))

        logger.debug("Scopes for Azure token endpoint: %s", deduplicated_scopes)
        return deduplicated_scopes

    def get_msal_app(self) -> ConfidentialClientApplication:
        """Get a pre-configured MSAL ConfidentialClientApplication for OBO token exchanges.

        This method creates an MSAL client using the same credentials configured for
        the AzureProvider, avoiding the need to duplicate configuration. The MSAL
        app can be used for On-Behalf-Of (OBO) token exchanges to call downstream
        APIs like Microsoft Graph.

        Returns:
            A configured ConfidentialClientApplication ready for OBO exchanges

        Raises:
            ImportError: If the `msal` package is not installed (requires fastmcp[azure])

        Example:
            ```python
            from fastmcp.server.dependencies import get_access_token

            @mcp.tool()
            async def call_graph():
                access_token = get_access_token()
                msal_app = mcp.auth.get_msal_app()

                result = msal_app.acquire_token_on_behalf_of(
                    user_assertion=access_token.token,
                    scopes=["https://graph.microsoft.com/User.Read"]
                )

                if "error" in result:
                    raise RuntimeError(result.get("error_description"))

                graph_token = result["access_token"]
                # Use graph_token to call Microsoft Graph APIs
            ```

        Note:
            For OBO to work, ensure the scopes you need are included in
            `additional_authorize_scopes` when configuring the AzureProvider,
            and that admin consent has been granted for those scopes.
        """
        try:
            from msal import ConfidentialClientApplication, TokenCache
        except ImportError as e:
            raise ImportError(
                "MSAL is required for get_msal_app(). "
                "Install with: pip install 'fastmcp[azure]'"
            ) from e

        authority = f"https://{self._base_authority}/{self._tenant_id}"

        return ConfidentialClientApplication(
            client_id=self._upstream_client_id,
            client_credential=self._upstream_client_secret.get_secret_value(),
            authority=authority,
            token_cache=TokenCache(),
        )


# --- Dependency injection support ---
# These require fastmcp[azure] extra for MSAL

# Check if DI engine is available
try:
    from docket.dependencies import Dependency
except ImportError:
    from fastmcp._vendor.docket_di import Dependency


def _require_msal(feature: str) -> None:
    """Raise ImportError with install instructions if MSAL is not available."""
    try:
        import msal  # noqa: F401
    except ImportError as e:
        raise ImportError(
            f"{feature} requires the `azure` extra. "
            "Install with: pip install 'fastmcp[azure]'"
        ) from e


class _MSALApp(Dependency):  # type: ignore[misc]
    """Dependency that provides a pre-configured MSAL ConfidentialClientApplication.

    Raises ImportError if fastmcp[azure] is not installed or if the auth provider
    is not an AzureProvider.
    """

    async def __aenter__(self) -> ConfidentialClientApplication:
        _require_msal("MSALApp")

        from fastmcp.server.dependencies import get_server

        server = get_server()
        if not isinstance(server.auth, AzureProvider):
            raise RuntimeError(
                "MSALApp requires an AzureProvider as the auth provider. "
                f"Current provider: {type(server.auth).__name__}"
            )

        return server.auth.get_msal_app()

    async def __aexit__(self, *args: object) -> None:
        pass


# Pre-instantiated singleton - no () needed when using as default
MSALApp: ConfidentialClientApplication = cast(
    "ConfidentialClientApplication", _MSALApp()
)
"""Get a pre-configured MSAL ConfidentialClientApplication as a dependency.

This dependency provides an MSAL client configured with the same credentials
as the AzureProvider. Use it for custom OBO scenarios or other MSAL operations.

Returns:
    A dependency that resolves to a ConfidentialClientApplication

Raises:
    ImportError: If fastmcp[azure] is not installed
    RuntimeError: If the auth provider is not an AzureProvider

Example:
    ```python
    from fastmcp.server.auth.providers.azure import MSALApp
    from fastmcp.server.dependencies import get_access_token
    from msal import ConfidentialClientApplication

    @mcp.tool()
    async def custom_obo(msal: ConfidentialClientApplication = MSALApp):
        token = get_access_token()
        result = msal.acquire_token_on_behalf_of(
            user_assertion=token.token,
            scopes=["https://graph.microsoft.com/.default"]
        )
        return result["access_token"]
    ```
"""


class _EntraOBOToken(Dependency):  # type: ignore[misc]
    """Dependency that performs OBO token exchange for Microsoft Entra.

    This dependency handles the complete On-Behalf-Of flow, exchanging the
    user's access token for a token that can call downstream APIs.
    """

    def __init__(self, scopes: list[str]):
        self.scopes = scopes

    async def __aenter__(self) -> str:
        _require_msal("EntraOBOToken")

        from fastmcp.server.dependencies import get_access_token, get_server

        # Get the current access token
        access_token = get_access_token()
        if access_token is None:
            raise RuntimeError(
                "No access token available. Cannot perform OBO exchange."
            )

        # Get the MSAL app from the server's auth provider
        server = get_server()
        if not isinstance(server.auth, AzureProvider):
            raise RuntimeError(
                "EntraOBOToken requires an AzureProvider as the auth provider. "
                f"Current provider: {type(server.auth).__name__}"
            )

        msal_app = server.auth.get_msal_app()

        # Perform the OBO exchange in a thread pool to avoid blocking the event loop
        # (MSAL uses synchronous requests under the hood)
        import asyncio

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: msal_app.acquire_token_on_behalf_of(
                user_assertion=access_token.token,
                scopes=self.scopes,
            ),
        )

        if "error" in result:
            error_desc = result.get("error_description", result.get("error"))
            raise RuntimeError(f"OBO token exchange failed: {error_desc}")

        return result["access_token"]

    async def __aexit__(self, *args: object) -> None:
        pass


def EntraOBOToken(scopes: list[str]) -> str:
    """Exchange the user's Entra token for a downstream API token via OBO.

    This dependency performs a Microsoft Entra On-Behalf-Of (OBO) token exchange,
    allowing your MCP server to call downstream APIs (like Microsoft Graph) on
    behalf of the authenticated user.

    Args:
        scopes: The scopes to request for the downstream API. For Microsoft Graph,
            use scopes like ["https://graph.microsoft.com/Mail.Read"] or
            ["https://graph.microsoft.com/.default"].

    Returns:
        A dependency that resolves to the downstream API access token string

    Raises:
        ImportError: If fastmcp[azure] is not installed
        RuntimeError: If no access token is available, provider is not Azure,
            or OBO exchange fails

    Example:
        ```python
        from fastmcp.server.auth.providers.azure import EntraOBOToken
        import httpx

        @mcp.tool()
        async def get_my_emails(
            graph_token: str = EntraOBOToken(["https://graph.microsoft.com/Mail.Read"])
        ):
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers={"Authorization": f"Bearer {graph_token}"}
                )
                return resp.json()
        ```

    Note:
        For OBO to work, ensure the scopes are included in the AzureProvider's
        `additional_authorize_scopes` parameter, and that admin consent has been
        granted for those scopes in your Entra app registration.
    """
    return cast(str, _EntraOBOToken(scopes))
