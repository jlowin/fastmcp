"""OAuth Proxy Provider for FastMCP.

This provider acts as a transparent proxy to an upstream OAuth Authorization Server
for providers that do not support Dynamic Client Registration (DCR). It uses static
client credentials and forwards OAuth flows to the upstream server.

Key features:
- Proxies authorization and token endpoints to upstream server
- Uses static client credentials (no DCR)
- Validates tokens using upstream JWKS
- Supports token refresh and revocation flows
- Enhanced logging with request correlation

This implementation is designed for production use with enterprise identity providers
that only support static client registration.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlencode

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.settings import (
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, AnyUrl, SecretStr, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from fastmcp.server.auth.auth import OAuthProvider, TokenVerifier
from fastmcp.server.dependencies import get_http_request
from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from starlette.routing import BaseRoute

logger = get_logger(__name__)

# Default token expiration times
DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS: Final[int] = 60 * 60  # 1 hour
DEFAULT_AUTH_CODE_EXPIRY_SECONDS: Final[int] = 5 * 60  # 5 minutes

# HTTP client timeout
HTTP_TIMEOUT_SECONDS: Final[int] = 30


class OAuthProxy(OAuthProvider):
    """OAuth provider that proxies requests to an upstream Authorization Server.

    This provider implements a transparent proxy pattern for providers that do not
    support Dynamic Client Registration (DCR). It uses static client credentials and:
    - Authorization flows redirect to the upstream server
    - Token exchange is forwarded to the upstream server
    - Token validation uses upstream JWKS
    - Maintains local state for token tracking and revocation

    This approach allows FastMCP to work with enterprise identity providers
    that only support static client registration.

    IMPORTANT ARCHITECTURAL NOTE:
    ============================
    This class inherits from OAuthProvider to leverage the standard OAuth route
    infrastructure provided by the MCP SDK. However, it uses a "bypass pattern"
    where certain OAuth methods (like exchange_authorization_code) are not used
    in the normal OAuth flow.

    Instead, the customize_auth_routes() method replaces the standard /token
    endpoint with a custom proxy handler (_handle_proxy_token_request) that
    forwards requests directly to the upstream server. This is necessary because:

    1. Standard OAuth validation requires local authorization code storage
    2. Proxies cannot validate codes they never generated
    3. All validation must be done by the upstream server
    4. The proxy just forwards requests transparently

    Methods like exchange_authorization_code() exist to satisfy the OAuthProvider
    interface but are intentionally not used in the proxy flow.
    """

    def __init__(
        self,
        *,
        # Upstream OAuth endpoints
        authorization_endpoint: str,
        token_endpoint: str,
        revocation_endpoint: str | None = None,
        # Upstream client credentials
        client_id: str,
        client_secret: str,
        # Token validation
        token_verifier: TokenVerifier,
        # URL configuration
        base_url: AnyHttpUrl | str,  # This FastMCP server's URL
        issuer_url: AnyHttpUrl | str | None = None,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
    ):
        """Initialize the OAuth proxy provider with explicit endpoints.

        Args:
            authorization_endpoint: Upstream authorization endpoint URL
            token_endpoint: Upstream token endpoint URL
            revocation_endpoint: Optional revocation endpoint URL
            client_id: Client ID for upstream server
            client_secret: Client secret for upstream server
            token_verifier: Token verifier for validating access tokens
            base_url: Public URL of this FastMCP server (for redirects, metadata, etc.)
            issuer_url: Optional issuer URL for OAuth metadata (defaults to base_url)
            service_documentation_url: Optional service documentation URL
            client_registration_options: Local client registration options
            revocation_options: Token revocation options
        """
        # Store upstream configuration
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._revocation_endpoint = revocation_endpoint

        # Client credentials
        self._client_id = client_id
        self._client_secret = SecretStr(client_secret)

        # Store base URL (this FastMCP server's URL)
        if isinstance(base_url, str):
            base_url = AnyHttpUrl(base_url)
        self.base_url = base_url

        # Token validator
        self._token_validator = token_verifier

        # Client storage and minimal token tracking for revocation
        self._clients: dict[str, OAuthClientInformationFull] = {}
        # Simple token storage for revocation tracking only
        # Note: Complex token relationships removed since proxy bypasses standard OAuth flows
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

        # Configure client registration and revocation options
        if client_registration_options is None:
            # Proxy mode supports client registration but always returns static credentials
            # This allows clients to "register" and get back the configured static credentials
            client_registration_options = ClientRegistrationOptions(enabled=True)

        if revocation_endpoint and revocation_options is None:
            revocation_options = RevocationOptions(enabled=True)

        super().__init__(
            base_url=base_url,
            issuer_url=issuer_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
            required_scopes=token_verifier.required_scopes,
        )

        logger.info(
            "Initialized OAuth proxy provider (revocation: %s)",
            bool(revocation_endpoint),
        )

    # -------------------------------------------------------------------------
    # Client Registration
    # -------------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get client information by ID.

        For unregistered clients, returns a temporary client object to allow
        the OAuth flow to proceed. The client will be properly registered
        during the register_client call.
        """
        client = self._clients.get(client_id)

        if client is None:
            # Create a temporary client to allow OAuth flow validation
            # We'll use a permissive redirect_uri list since upstream will validate
            redirect_uris: list[AnyUrl] = [self.base_url]  # type: ignore[list-item]

            # Try to extract redirect_uri from current request context
            try:
                req = get_http_request()
                maybe_redirect = req.query_params.get("redirect_uri")
                if maybe_redirect:
                    try:
                        redirect_uri = AnyUrl(maybe_redirect)
                        redirect_uris.insert(0, redirect_uri)
                    except ValidationError:
                        logger.warning(
                            "Invalid redirect_uri in request: %s", maybe_redirect
                        )
            except Exception:
                # No active request context or other error - use defaults
                pass

            client = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=None,
                redirect_uris=redirect_uris,
                grant_types=["authorization_code", "refresh_token"],
                token_endpoint_auth_method="none",
            )

            logger.debug("Created temporary client for %s", client_id)

        return client

    async def register_client(
        self, client_info: OAuthClientInformationFull
    ) -> OAuthClientInformationFull:
        """Register a client using configured static credentials.

        Proxy mode does not support DCR - all clients use the static credentials
        configured when the proxy was created.
        """
        # Use configured static credentials
        registered_client = OAuthClientInformationFull(
            **client_info.model_dump(
                exclude={
                    "client_id",
                    "client_secret",
                    "grant_types",
                    "token_endpoint_auth_method",
                }
            ),
            client_id=self._client_id,
            client_secret=self._client_secret.get_secret_value(),
            grant_types=client_info.grant_types
            or ["authorization_code", "refresh_token"],
            token_endpoint_auth_method="none",
        )

        # Store the client registration under both original and configured IDs
        self._clients[self._client_id] = registered_client
        self._clients[client_info.client_id] = registered_client

        logger.info(
            "Registered client %s with configured credentials (%d redirect URIs)",
            self._client_id,
            len(registered_client.redirect_uris),
        )

        return registered_client

    # -------------------------------------------------------------------------
    # Authorization Flow (Proxy to Upstream)
    # -------------------------------------------------------------------------

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        breakpoint()
        """Redirect authorization request to upstream server.

        Builds the upstream authorization URL with the client's parameters
        and returns it for redirection. The upstream server handles the
        user authentication and consent flow.
        """
        logger.info("Authorization request for client: %s", client.client_id)

        # Build query parameters for upstream authorization request
        query_params: dict[str, Any] = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": str(params.redirect_uri),
            "state": params.state,
        }
        # Add PKCE parameters if present
        if params.code_challenge:
            query_params["code_challenge"] = params.code_challenge
            query_params["code_challenge_method"] = "S256"

        # Add scopes if present
        if params.scopes:
            query_params["scope"] = " ".join(params.scopes)

        # Build the upstream authorization URL
        upstream_url = f"{self._authorization_endpoint}?{urlencode(query_params)}"

        logger.info(
            "Redirecting authorization request to upstream server for client %s",
            client.client_id,
        )
        logger.debug("Upstream authorization URL: %s", upstream_url)

        return upstream_url

    # -------------------------------------------------------------------------
    # Authorization Code Handling
    # -------------------------------------------------------------------------

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        """Load authorization code for validation.

        Since we can't introspect codes from the upstream server, we create
        a minimal AuthorizationCode object that will be used in the token
        exchange process.
        """
        # Create a minimal authorization code object for the exchange process
        return AuthorizationCode(
            code=authorization_code,
            client_id=client.client_id,
            redirect_uri=self.base_url,  # Placeholder - actual value extracted from request
            redirect_uri_provided_explicitly=False,
            scopes=[],  # Will be determined by upstream server
            expires_at=int(time.time() + DEFAULT_AUTH_CODE_EXPIRY_SECONDS),
            code_challenge="",  # Placeholder - not validated in proxy mode
        )

    async def _request_token_from_upstream(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Request token from upstream server using authorization code.

        NOTE: This method is NOT used in the standard proxy flow. It exists for
        subclasses (like WorkOS) that may want to override token exchange logic
        for testing or SDK integration purposes.

        The actual token exchange in proxy mode is handled by _handle_proxy_token_request
        which forwards HTTP requests directly to the upstream server.
        """
        # Base token request data using configured credentials
        token_data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret.get_secret_value(),
            "code": authorization_code.code,
        }

        # Extract additional parameters from the current request
        try:
            req = get_http_request()
            if req.method == "POST":
                form = await req.form()
                # Forward relevant fields to upstream
                for field in ("redirect_uri", "code_verifier", "resource", "scope"):
                    if field in form and form[field]:
                        token_data[field] = str(form[field])
        except Exception as e:
            logger.warning("Could not extract form data from request: %s", e)

        # Ensure redirect_uri is present (required by some providers)
        if "redirect_uri" not in token_data:
            token_data["redirect_uri"] = str(authorization_code.redirect_uri)

        # Make the token request to upstream server
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
            try:
                response = await http_client.post(self._token_endpoint, data=token_data)

                if response.status_code >= 400:
                    logger.error(
                        "Upstream token exchange failed: %d", response.status_code
                    )
                    raise TokenError(
                        "invalid_grant", f"Upstream token error {response.status_code}"
                    )

                token_data = response.json()
                return OAuthToken(**token_data)  # type: ignore[arg-type]

            except httpx.RequestError as e:
                logger.error("Failed to connect to upstream token endpoint: %s", e)
                raise TokenError(
                    "invalid_grant", "Unable to connect to upstream server"
                ) from e

    def _store_token_response(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
        token_response: OAuthToken,
    ) -> None:
        """Store tokens from response for local tracking and management.

        This method handles the common token storage logic that should be
        consistent across all proxy implementations.
        """
        # Extract token information
        access_token_value = token_response.access_token
        refresh_token_value = token_response.refresh_token
        if token_response.expires_in:
            expires_at = int(time.time() + token_response.expires_in)
        else:
            expires_at = int(time.time() + DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS)

        # Store access token locally for tracking
        access_token = AccessToken(
            token=access_token_value,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=expires_at,
        )
        self._access_tokens[access_token_value] = access_token

        # Store refresh token if provided
        if refresh_token_value:
            refresh_token = RefreshToken(
                token=refresh_token_value,
                client_id=client.client_id,
                scopes=authorization_code.scopes,
                expires_at=None,  # Refresh tokens typically don't expire
            )
            self._refresh_tokens[refresh_token_value] = refresh_token

        logger.info(
            "Successfully stored tokens for tracking (client: %s)",
            client.client_id,
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Exchange authorization code for tokens - NOT USED IN PROXY MODE.

        This method exists to satisfy the OAuthProvider interface but is never
        called in the proxy flow. The customize_auth_routes() method replaces
        the standard /token endpoint with _handle_proxy_token_request, which
        bypasses this method entirely.

        Token exchanges are handled directly by the proxy endpoint to avoid
        OAuth validation that cannot be performed without local auth code storage.
        """
        raise NotImplementedError(
            "exchange_authorization_code is not used in proxy mode. "
            "Token exchanges are handled by the custom proxy /token endpoint."
        )

    # -------------------------------------------------------------------------
    # Refresh Token Flow
    # -------------------------------------------------------------------------

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        """Load refresh token from local storage."""
        return self._refresh_tokens.get(refresh_token)

    async def _request_refresh_token_from_upstream(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Request new access token from upstream server using refresh token.

        NOTE: This method is NOT used in the standard proxy flow. It exists for
        subclasses (like WorkOS) that may want to override refresh token logic
        for testing or SDK integration purposes.

        The actual refresh token exchange in proxy mode is handled by
        _handle_proxy_token_request which forwards HTTP requests directly
        to the upstream server.
        """
        refresh_data = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret.get_secret_value(),
            "refresh_token": refresh_token.token,
        }

        # Add scopes if requested
        if scopes:
            refresh_data["scope"] = " ".join(scopes)

        # Make refresh request to upstream server
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
            try:
                response = await http_client.post(
                    self._token_endpoint, data=refresh_data
                )

                if response.status_code >= 400:
                    logger.error(
                        "Upstream refresh token exchange failed: %d",
                        response.status_code,
                    )
                    raise TokenError(
                        "invalid_grant", "Upstream refresh token exchange failed"
                    )

                token_data = response.json()
                return OAuthToken(**token_data)  # type: ignore[arg-type]

            except httpx.RequestError as e:
                logger.error("Failed to connect to upstream token endpoint: %s", e)
                raise TokenError(
                    "invalid_grant", "Unable to connect to upstream server"
                ) from e

    def _store_refresh_token_response(
        self,
        client: OAuthClientInformationFull,
        old_refresh_token: RefreshToken,
        scopes: list[str],
        token_response: OAuthToken,
    ) -> None:
        """Store refreshed tokens for local tracking and management.

        This method handles the common refresh token storage logic including
        token rotation that should be consistent across all proxy implementations.
        """
        # Update local token storage
        new_access_token = token_response.access_token
        if token_response.expires_in:
            expires_at = int(time.time() + token_response.expires_in)
        else:
            expires_at = int(time.time() + DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS)

        self._access_tokens[new_access_token] = AccessToken(
            token=new_access_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=expires_at,
        )

        # Handle refresh token rotation if new one provided
        if (
            token_response.refresh_token
            and token_response.refresh_token != old_refresh_token.token
        ):
            new_refresh_token = token_response.refresh_token
            # Remove old refresh token and store new one
            self._refresh_tokens.pop(old_refresh_token.token, None)
            self._refresh_tokens[new_refresh_token] = RefreshToken(
                token=new_refresh_token,
                client_id=client.client_id,
                scopes=scopes,
                expires_at=None,
            )

        logger.info(
            "Successfully stored refreshed tokens for tracking (client: %s)",
            client.client_id,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Exchange refresh token for new access token - NOT USED IN PROXY MODE.

        This method exists to satisfy the OAuthProvider interface but is never
        called in the proxy flow. The customize_auth_routes() method replaces
        the standard /token endpoint with _handle_proxy_token_request, which
        handles ALL token requests (authorization_code and refresh_token grants)
        by forwarding them directly to the upstream server.
        """
        raise NotImplementedError(
            "exchange_refresh_token is not used in proxy mode. "
            "All token requests are handled by the custom proxy /token endpoint."
        )

    # -------------------------------------------------------------------------
    # Token Validation
    # -------------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Validate access token using upstream JWKS.

        Delegates to the JWT verifier which handles signature validation,
        expiration checking, and claims validation using the upstream JWKS.
        """
        return await self._token_validator.verify_token(token)

    # -------------------------------------------------------------------------
    # Token Revocation
    # -------------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Revoke token locally and with upstream server if supported.

        Removes tokens from local storage and attempts to revoke them with
        the upstream server if a revocation endpoint is configured.
        """
        # Clean up local token storage
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        else:  # RefreshToken
            self._refresh_tokens.pop(token.token, None)

        # Attempt upstream revocation if endpoint is configured
        if self._revocation_endpoint:
            try:
                async with httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT_SECONDS
                ) as http_client:
                    await http_client.post(
                        self._revocation_endpoint,
                        data={"token": token.token},
                        auth=(self._client_id, self._client_secret.get_secret_value()),
                    )
                    logger.info("Successfully revoked token with upstream server")
            except Exception as e:
                logger.warning("Failed to revoke token with upstream server: %s", e)
        else:
            logger.debug("No revocation endpoint configured")

        logger.info("Token revoked successfully")

    # -------------------------------------------------------------------------
    # Custom Route Handling
    # -------------------------------------------------------------------------

    async def _handle_proxy_token_request(self, request: Request) -> JSONResponse:
        """Custom token endpoint that forwards requests to upstream server.

        This handler intercepts token requests and forwards them to the upstream
        OAuth server while preserving all request parameters (including PKCE).
        """
        try:
            # Parse the incoming request form data
            form_data = await request.form()
            form_dict = dict(form_data)

            # Build the upstream request data with configured credentials
            upstream_data = {
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
            }

            # Forward all relevant form fields (except our credentials)
            for key, value in form_dict.items():
                if key not in {"client_id", "client_secret"}:
                    upstream_data[key] = str(value)

            # Make the request to upstream server
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
                response = await http_client.post(
                    self._token_endpoint,
                    data=upstream_data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                )

                # Handle error responses
                if response.status_code >= 400:
                    logger.warning(
                        "Upstream token request failed: %d", response.status_code
                    )
                    try:
                        error_data = response.json()
                    except Exception:
                        error_data = {
                            "error": "server_error",
                            "error_description": "Upstream server error",
                        }
                    return JSONResponse(
                        content=error_data, status_code=response.status_code
                    )

                # Success - process the token response
                token_data = response.json()

                # Store tokens locally for tracking (authorization_code grant only)
                if (
                    upstream_data.get("grant_type") == "authorization_code"
                    and "access_token" in token_data
                ):
                    try:
                        self._store_tokens_from_response(token_data, self._client_id)
                    except Exception as e:
                        logger.warning("Failed to store tokens: %s", e)

                logger.info("Successfully proxied token request to upstream server")
                return JSONResponse(content=token_data)

        except httpx.RequestError as e:
            logger.error("Failed to connect to upstream token endpoint: %s", e)
            return JSONResponse(
                content={
                    "error": "server_error",
                    "error_description": "Unable to connect to upstream server",
                },
                status_code=503,
            )
        except Exception as e:
            logger.error("Error in proxy token handler: %s", e, exc_info=True)
            return JSONResponse(
                content={
                    "error": "server_error",
                    "error_description": "Internal server error",
                },
                status_code=500,
            )

    def _store_tokens_from_response(
        self, token_data: dict[str, Any], client_id: str
    ) -> None:
        """Store tokens from upstream response for local tracking."""
        try:
            access_token_value = token_data.get("access_token")
            refresh_token_value = token_data.get("refresh_token")
            expires_in = int(
                token_data.get("expires_in", DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS)
            )
            expires_at = int(time.time() + expires_in)

            if access_token_value:
                access_token = AccessToken(
                    token=access_token_value,
                    client_id=client_id,
                    scopes=[],  # Will be determined by token validation
                    expires_at=expires_at,
                )
                self._access_tokens[access_token_value] = access_token

                if refresh_token_value:
                    refresh_token = RefreshToken(
                        token=refresh_token_value,
                        client_id=client_id,
                        scopes=[],
                        expires_at=None,
                    )
                    self._refresh_tokens[refresh_token_value] = refresh_token

                logger.debug("Stored tokens from upstream response for tracking")

        except Exception as e:
            logger.warning("Failed to store tokens from upstream response: %s", e)

    def customize_auth_routes(self, routes: list[BaseRoute]) -> list[BaseRoute]:
        """Override to replace the token endpoint with our proxy handler.

        This method replaces the standard token endpoint with a custom handler
        that forwards requests to the upstream OAuth server while preserving
        all parameters and proper error handling.
        """
        custom_routes = []

        for route in routes:
            # Replace the token endpoint with our proxy handler
            if (
                isinstance(route, Route)
                and route.path == "/token"
                and route.methods is not None
                and "POST" in route.methods
            ):
                logger.debug("Replacing standard token endpoint with proxy handler")
                custom_routes.append(
                    Route(
                        path="/token",
                        endpoint=self._handle_proxy_token_request,
                        methods=["POST"],
                    )
                )
            else:
                # Keep all other routes unchanged (including /register)
                custom_routes.append(route)

        logger.info(
            "Customized OAuth routes for proxy behavior (replaced token endpoint)"
        )
        return custom_routes

    # -------------------------------------------------------------------------
    # Discovery Support
    # -------------------------------------------------------------------------

    @classmethod
    async def from_discovery(
        cls,
        discovery_issuer_url: str,
        *,
        client_id: str,
        client_secret: str,
        token_verifier: TokenVerifier,
        base_url: AnyHttpUrl | str,
        # Optional endpoint overrides
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        revocation_endpoint: str | None = None,
        # Other options
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
    ) -> OAuthProxy:
        """Create OAuthProxy using OpenID Connect Discovery.

        Fetches OAuth server metadata from {discovery_issuer_url}/.well-known/oauth-authorization-server
        and uses discovered endpoints unless explicitly overridden.

        Args:
            discovery_issuer_url: Base URL of the OAuth server (used for discovery)
            client_id: Client ID for upstream server
            client_secret: Client secret for upstream server
            token_verifier: Token verifier for validating access tokens
            base_url: Public URL of this FastMCP server
            authorization_endpoint: Override discovered authorization endpoint
            token_endpoint: Override discovered token endpoint
            revocation_endpoint: Override discovered revocation endpoint
            service_documentation_url: Optional service documentation URL
            client_registration_options: Local client registration options
            revocation_options: Token revocation options

        Returns:
            Configured OAuthProxy instance

        Raises:
            ValueError: If discovery fails or required endpoints are missing
        """
        discovery_url = (
            f"{discovery_issuer_url.rstrip('/')}/.well-known/oauth-authorization-server"
        )

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
                response = await http_client.get(discovery_url)
                response.raise_for_status()
                metadata = response.json()
        except httpx.RequestError as e:
            raise ValueError(
                f"Discovery failed: unable to connect to {discovery_url}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Discovery failed: {e.response.status_code} from {discovery_url}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Discovery failed: unable to parse metadata from {discovery_url}"
            ) from e

        # Use overrides or discovered endpoints
        final_authorization_endpoint = authorization_endpoint or metadata.get(
            "authorization_endpoint"
        )
        final_token_endpoint = token_endpoint or metadata.get("token_endpoint")
        final_revocation_endpoint = revocation_endpoint or metadata.get(
            "revocation_endpoint"
        )

        # Validate required endpoints
        if not final_authorization_endpoint:
            raise ValueError("No authorization_endpoint found in discovery metadata")
        if not final_token_endpoint:
            raise ValueError("No token_endpoint found in discovery metadata")

        logger.info(
            "Discovered OAuth endpoints: authorization=%s, token=%s, revocation=%s",
            final_authorization_endpoint,
            final_token_endpoint,
            final_revocation_endpoint or "None",
        )

        return cls(
            authorization_endpoint=final_authorization_endpoint,
            token_endpoint=final_token_endpoint,
            revocation_endpoint=final_revocation_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            token_verifier=token_verifier,
            base_url=base_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
        )
