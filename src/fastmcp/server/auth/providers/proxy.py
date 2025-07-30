"""OAuth Proxy Provider for FastMCP.

This provider acts as a transparent proxy to an upstream OAuth Authorization Server,
automatically detecting and handling Dynamic Client Registration (DCR) capabilities.
It works with both DCR-enabled providers (like WorkOS AuthKit) and legacy providers
that only support static client registration.

Key features:
- Auto-detects DCR support via .well-known/oauth-authorization-server discovery
- Forwards real DCR requests when upstream supports it
- Falls back to local DCR simulation with fixed credentials for legacy providers
- Proxies authorization and token endpoints to upstream server
- Validates tokens using upstream JWKS
- Maintains minimal local state for bookkeeping
- Enhanced logging with request correlation

This implementation is based on the OAuth 2.1 specification and is designed for
production use with both modern and enterprise identity providers.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
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

    This provider implements a transparent proxy pattern where:
    - Auto-detects DCR support via OAuth 2.0 discovery
    - Forwards real DCR requests when upstream supports it
    - Falls back to local DCR simulation with fixed credentials for legacy providers
    - Authorization flows redirect to the upstream server
    - Token exchange is forwarded to the upstream server
    - Token validation uses upstream JWKS
    - Minimal local state is maintained for bookkeeping

    This approach allows FastMCP to work with both modern providers (WorkOS AuthKit)
    and enterprise identity providers that don't support Dynamic Client Registration.
    """

    def __init__(
        self,
        *,
        # Upstream OAuth endpoints (all explicit)
        authorization_endpoint: str,
        token_endpoint: str,
        registration_endpoint: str | None = None,  # DCR enabled if provided
        revocation_endpoint: str | None = None,
        # Upstream client credentials
        client_id: str,
        client_secret: str,
        # Token validation
        token_verifier: TokenVerifier,
        # FastMCP server configuration
        issuer_url: AnyHttpUrl | str,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
    ):
        """Initialize the OAuth proxy provider with explicit endpoints.

        Args:
            authorization_endpoint: Upstream authorization endpoint URL
            token_endpoint: Upstream token endpoint URL
            registration_endpoint: Optional DCR endpoint URL (enables real DCR if provided)
            revocation_endpoint: Optional revocation endpoint URL
            client_id: Client ID for upstream server (or fallback for DCR)
            client_secret: Client secret for upstream server (or fallback for DCR)
            token_verifier: Token verifier for validating access tokens
            issuer_url: Public URL of this FastMCP server (used in metadata)
            service_documentation_url: Optional service documentation URL
            client_registration_options: Local client registration options
            revocation_options: Token revocation options

        Use OAuthProxy.from_discovery() for auto-endpoint discovery.
        """
        # Store upstream configuration
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._registration_endpoint = registration_endpoint
        self._revocation_endpoint = revocation_endpoint

        # Client credentials
        self._client_id = client_id
        self._client_secret = SecretStr(client_secret)

        # DCR support is simple: enabled if registration endpoint provided
        self._supports_dcr = registration_endpoint is not None

        # Token validator
        self._token_validator = token_verifier

        # Client and token storage
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._client_credentials: dict[
            str, tuple[str, str]
        ] = {}  # For DCR: client_id -> (actual_id, secret)
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        self._access_to_refresh: dict[str, str] = {}
        self._refresh_to_access: dict[str, str] = {}

        # Configure DCR and revocation options
        if client_registration_options is None:
            client_registration_options = ClientRegistrationOptions(enabled=True)

        if revocation_endpoint and revocation_options is None:
            revocation_options = RevocationOptions(enabled=True)

        super().__init__(
            issuer_url=issuer_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
            required_scopes=token_verifier.required_scopes,
        )

        logger.info(
            "Initialized OAuth proxy provider (DCR: %s, revocation: %s)",
            self._supports_dcr,
            bool(revocation_endpoint),
        )

    @classmethod
    async def from_discovery(
        cls,
        discovery_issuer_url: str,
        *,
        # Optional endpoint overrides (same names as constructor)
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        registration_endpoint: str | None = None,
        revocation_endpoint: str | None = None,
        # Required parameters (same as constructor)
        client_id: str,
        client_secret: str,
        token_verifier: TokenVerifier,
        **kwargs,  # Pass through any other constructor args
    ) -> OAuthProxy:
        """Create OAuth proxy by discovering endpoints from issuer URL.

        Args:
            discovery_issuer_url: Base URL of OAuth server for discovery
            authorization_endpoint: Override discovered authorization endpoint
            token_endpoint: Override discovered token endpoint
            registration_endpoint: Override discovered registration endpoint (or force enable/disable DCR)
            revocation_endpoint: Override discovered revocation endpoint
            client_id: Client credentials for upstream server
            client_secret: Client secret for upstream server
            token_verifier: Token verifier for access token validation
            **kwargs: Additional arguments passed to constructor (including issuer_url for FastMCP server)

        Returns:
            Configured OAuthProxy instance

        Raises:
            ValueError: If discovery fails and no overrides provided
            httpx.RequestError: If unable to connect to discovery endpoint
        """
        discovery_url = (
            f"{discovery_issuer_url.rstrip('/')}/.well-known/oauth-authorization-server"
        )
        logger.debug("Discovering OAuth endpoints at %s", discovery_url)

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
                response = await http_client.get(discovery_url)

                if response.status_code != 200:
                    raise ValueError(
                        f"Discovery failed with status {response.status_code}: {response.text[:200]}"
                    )

                metadata = response.json()
                logger.info("Successfully discovered OAuth metadata")

        except httpx.RequestError as e:
            logger.error("Failed to connect to discovery endpoint: %s", e)
            raise ValueError(
                f"Discovery failed: unable to connect to {discovery_url}"
            ) from e

        # Extract endpoints with overrides taking precedence
        final_authorization_endpoint = authorization_endpoint or metadata.get(
            "authorization_endpoint"
        )
        final_token_endpoint = token_endpoint or metadata.get("token_endpoint")
        final_registration_endpoint = registration_endpoint or metadata.get(
            "registration_endpoint"
        )
        final_revocation_endpoint = revocation_endpoint or metadata.get(
            "revocation_endpoint"
        )

        # Validate required endpoints
        if not final_authorization_endpoint:
            raise ValueError(
                "No authorization_endpoint found in discovery or overrides"
            )
        if not final_token_endpoint:
            raise ValueError("No token_endpoint found in discovery or overrides")

        logger.info(
            "Using endpoints: auth=%s, token=%s, dcr=%s, revoke=%s",
            final_authorization_endpoint,
            final_token_endpoint,
            bool(final_registration_endpoint),
            bool(final_revocation_endpoint),
        )

        # Create instance with discovered/overridden endpoints
        return cls(
            authorization_endpoint=final_authorization_endpoint,
            token_endpoint=final_token_endpoint,
            registration_endpoint=final_registration_endpoint,
            revocation_endpoint=final_revocation_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            token_verifier=token_verifier,
            **kwargs,
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
            redirect_uris: list[AnyUrl] = [self.issuer_url]  # type: ignore[list-item]

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
        """Register a client using DCR forwarding or configured credentials.

        If registration_endpoint was provided, forwards the registration request.
        Otherwise, uses configured credentials for all clients.
        """
        if self._supports_dcr:
            return await self._forward_dcr_registration(client_info)
        else:
            return await self._register_with_configured_credentials(client_info)

    async def _forward_dcr_registration(
        self, client_info: OAuthClientInformationFull
    ) -> OAuthClientInformationFull:
        """Forward DCR request to upstream server."""
        # Prepare registration request
        registration_data = client_info.model_dump(
            exclude_none=True,
            exclude={
                "client_id",
                "client_secret",
            },  # These will be assigned by upstream
            mode="json",  # Convert Pydantic types (like AnyUrl) to JSON-serializable values
        )

        # Ensure token_endpoint_auth_method is set to "none" for public clients
        registration_data["token_endpoint_auth_method"] = "none"

        # Convert scope string to array if needed for better DCR compatibility
        if "scope" in registration_data and isinstance(registration_data["scope"], str):
            scopes = registration_data["scope"].split()
            registration_data["scope"] = " ".join(
                scopes
            )  # Keep as string but normalize
            # Some providers may prefer scopes as an array
            # registration_data["scopes"] = scopes

        logger.info("Forwarding DCR request to upstream: %s", registration_data)

        if not self._registration_endpoint:
            raise TokenError("invalid_client", "DCR not supported")

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
                response = await http_client.post(
                    self._registration_endpoint,
                    json=registration_data,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code >= 400:
                    logger.error(
                        "Upstream DCR failed: %d - %s",
                        response.status_code,
                        response.text[:500],
                    )
                    raise TokenError(
                        "invalid_client",
                        f"Upstream registration failed: {response.status_code}",
                    )

                upstream_client_data = response.json()

                # Create registered client with upstream response
                upstream_client_data_dict = upstream_client_data
                upstream_client_id = upstream_client_data_dict["client_id"]
                original_client_id = client_info.client_id

                # Create client with ORIGINAL client ID but upstream credentials
                registered_client = OAuthClientInformationFull(
                    **{**upstream_client_data_dict, "client_id": original_client_id}
                )

                # Store the registered client info under both IDs
                self._clients[upstream_client_id] = registered_client
                self._clients[original_client_id] = registered_client

                # Store credentials mapping: original client ID -> upstream credentials
                self._client_credentials[original_client_id] = (
                    upstream_client_id,
                    upstream_client_data_dict.get("client_secret", ""),
                )

                logger.info(
                    "Successfully registered client %s (upstream: %s) via upstream DCR",
                    original_client_id,
                    upstream_client_id,
                )
                logger.info(
                    "DCR credentials mapping: %s -> %s",
                    original_client_id,
                    upstream_client_id,
                )

                return registered_client

        except httpx.RequestError as e:
            logger.error("Failed to connect to upstream DCR endpoint: %s", e)
            raise TokenError(
                "invalid_client", "Unable to connect to upstream registration server"
            ) from e

    async def _register_with_configured_credentials(
        self, client_info: OAuthClientInformationFull
    ) -> OAuthClientInformationFull:
        """Register client using configured credentials (no DCR mode)."""
        # Use the configured credentials
        configured_id = self._client_id
        configured_secret = self._client_secret.get_secret_value()

        # Merge client metadata with configured credentials
        registered_client = OAuthClientInformationFull(
            **client_info.model_dump(
                exclude={
                    "client_id",
                    "client_secret",
                    "grant_types",
                    "token_endpoint_auth_method",
                }
            ),
            client_id=configured_id,
            client_secret=configured_secret,
            grant_types=client_info.grant_types
            or ["authorization_code", "refresh_token"],
            token_endpoint_auth_method="none",
        )

        # Store the client registration and its credentials
        original_client_id = client_info.client_id

        # Store client info under both IDs
        self._clients[configured_id] = registered_client
        self._clients[original_client_id] = registered_client

        # Store credentials mapping: original client ID -> configured credentials
        self._client_credentials[original_client_id] = (
            configured_id,
            configured_secret,
        )

        logger.info(
            "Registered client %s with configured credentials (%d redirect URIs)",
            configured_id,
            len(registered_client.redirect_uris),
        )

        return registered_client

    # -------------------------------------------------------------------------
    # Authorization Flow (Proxy to Upstream)
    # -------------------------------------------------------------------------

    def _get_client_credentials(self, client_id: str) -> tuple[str, str]:
        """Get the actual credentials to use for a client."""
        if client_id in self._client_credentials:
            return self._client_credentials[client_id]
        else:
            # Use the configured credentials
            return self._client_id, self._client_secret.get_secret_value()

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Redirect authorization request to upstream server.

        Builds the upstream authorization URL with the client's parameters
        and returns it for redirection. The upstream server handles the
        user authentication and consent flow.
        """
        # Get the actual credentials to use for this client
        logger.info("Authorization request for client: %s", client.client_id)
        actual_client_id, _ = self._get_client_credentials(client.client_id)
        logger.info("Mapped to upstream client: %s", actual_client_id)

        # Build query parameters for upstream authorization request
        query_params: dict[str, Any] = {
            "response_type": "code",
            "client_id": actual_client_id,
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
            redirect_uri=self.issuer_url,  # Placeholder - actual value extracted from request
            redirect_uri_provided_explicitly=False,
            scopes=[],  # Will be determined by upstream server
            expires_at=int(time.time() + DEFAULT_AUTH_CODE_EXPIRY_SECONDS),
            code_challenge="",  # Placeholder - not validated in proxy mode
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Exchange authorization code for tokens with upstream server.

        Forwards the token request to the upstream server and returns the
        response. Also stores tokens locally for refresh and revocation tracking.
        """
        # Get the actual credentials to use for this client
        actual_client_id, actual_client_secret = self._get_client_credentials(
            client.client_id
        )

        # Base token request data
        token_data = {
            "grant_type": "authorization_code",
            "client_id": actual_client_id,
            "client_secret": actual_client_secret,
            "code": authorization_code.code,
        }

        # Extract additional parameters from the current request
        try:
            req = get_http_request()
            if req.method == "POST":
                form = await req.form()

                # Log the incoming request (with sensitive data redacted)
                redacted_form = {
                    k: (
                        str(v)[:8] + "..."
                        if k in {"code", "code_verifier", "client_secret"} and v
                        else str(v)
                    )
                    for k, v in form.items()
                }
                logger.debug("Token request form data: %s", redacted_form)

                # Forward relevant fields to upstream
                for field in ("redirect_uri", "code_verifier", "resource", "scope"):
                    if field in form and form[field]:
                        token_data[field] = str(form[field])
        except Exception as e:
            logger.warning("Could not extract form data from request: %s", e)

        # Ensure redirect_uri is present (required by some providers)
        if "redirect_uri" not in token_data:
            token_data["redirect_uri"] = str(authorization_code.redirect_uri)

        # Log outgoing request (with sensitive data redacted)
        redacted_data = {
            k: (
                "***"
                if k == "client_secret"
                else (str(v)[:8] + "..." if k in {"code", "code_verifier"} else str(v))
            )
            for k, v in token_data.items()
        }
        logger.debug("Forwarding token request to upstream: %s", redacted_data)

        # Make the token request to upstream server
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
            try:
                response = await http_client.post(self._token_endpoint, data=token_data)

                logger.debug(
                    "Upstream token response: status=%d, body_preview=%s",
                    response.status_code,
                    response.text[:200] + ("..." if len(response.text) > 200 else ""),
                )

                if response.status_code >= 400:
                    logger.error(
                        "Upstream token exchange failed: %d - %s",
                        response.status_code,
                        response.text[:500],
                    )
                    raise TokenError(
                        "invalid_grant", f"Upstream token error {response.status_code}"
                    )

                token_response: Mapping[str, Any] = response.json()

            except httpx.RequestError as e:
                logger.error("Failed to connect to upstream token endpoint: %s", e)
                raise TokenError(
                    "invalid_grant", "Unable to connect to upstream server"
                ) from e

        # Extract token information
        access_token_value = token_response["access_token"]
        refresh_token_value = token_response.get("refresh_token")
        expires_in = int(
            token_response.get("expires_in", DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS)
        )
        expires_at = int(time.time() + expires_in)

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

            # Maintain token relationships for cleanup
            self._access_to_refresh[access_token_value] = refresh_token_value
            self._refresh_to_access[refresh_token_value] = access_token_value

        logger.info(
            "Successfully exchanged authorization code for tokens (client: %s)",
            client.client_id,
        )

        return OAuthToken(**token_response)  # type: ignore[arg-type]

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

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Exchange refresh token for new access token with upstream server."""
        # Get the actual credentials to use for this client
        actual_client_id, actual_client_secret = self._get_client_credentials(
            client.client_id
        )

        refresh_data = {
            "grant_type": "refresh_token",
            "client_id": actual_client_id,
            "client_secret": actual_client_secret,
            "refresh_token": refresh_token.token,
        }

        # Add scopes if requested
        if scopes:
            refresh_data["scope"] = " ".join(scopes)

        # Log request (with sensitive data redacted)
        redacted_data = {
            k: (
                "***"
                if k == "client_secret"
                else (str(v)[:8] + "..." if k == "refresh_token" else str(v))
            )
            for k, v in refresh_data.items()
        }
        logger.debug("Forwarding refresh token request to upstream: %s", redacted_data)

        # Make refresh request to upstream server
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
            try:
                response = await http_client.post(
                    self._token_endpoint, data=refresh_data
                )

                logger.debug(
                    "Upstream refresh token response: status=%d, body_preview=%s",
                    response.status_code,
                    response.text[:200] + ("..." if len(response.text) > 200 else ""),
                )

                if response.status_code >= 400:
                    logger.error(
                        "Upstream refresh token exchange failed: %d - %s",
                        response.status_code,
                        response.text[:500],
                    )
                    raise TokenError(
                        "invalid_grant", "Upstream refresh token exchange failed"
                    )

                token_response: Mapping[str, Any] = response.json()

            except httpx.RequestError as e:
                logger.error("Failed to connect to upstream token endpoint: %s", e)
                raise TokenError(
                    "invalid_grant", "Unable to connect to upstream server"
                ) from e

        # Update local token storage
        new_access_token = token_response["access_token"]
        expires_in = int(
            token_response.get("expires_in", DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS)
        )

        self._access_tokens[new_access_token] = AccessToken(
            token=new_access_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(time.time() + expires_in),
        )

        # Handle refresh token rotation if new one provided
        if "refresh_token" in token_response:
            new_refresh_token = token_response["refresh_token"]
            if new_refresh_token != refresh_token.token:
                # Remove old refresh token
                self._refresh_tokens.pop(refresh_token.token, None)
                old_access = self._refresh_to_access.pop(refresh_token.token, None)
                if old_access:
                    self._access_to_refresh.pop(old_access, None)

                # Store new refresh token
                self._refresh_tokens[new_refresh_token] = RefreshToken(
                    token=new_refresh_token,
                    client_id=client.client_id,
                    scopes=scopes,
                    expires_at=None,
                )
                self._access_to_refresh[new_access_token] = new_refresh_token
                self._refresh_to_access[new_refresh_token] = new_access_token

        logger.info(
            "Successfully refreshed access token (client: %s)", client.client_id
        )

        return OAuthToken(**token_response)  # type: ignore[arg-type]

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
            # Also remove associated refresh token
            paired_refresh = self._access_to_refresh.pop(token.token, None)
            if paired_refresh:
                self._refresh_tokens.pop(paired_refresh, None)
                self._refresh_to_access.pop(paired_refresh, None)
        else:  # RefreshToken
            self._refresh_tokens.pop(token.token, None)
            # Also remove associated access token
            paired_access = self._refresh_to_access.pop(token.token, None)
            if paired_access:
                self._access_tokens.pop(paired_access, None)
                self._access_to_refresh.pop(paired_access, None)

        # Attempt upstream revocation if endpoint is configured
        if self._revocation_endpoint:
            try:
                # Get the credentials that were used for this token's client
                actual_client_id, actual_client_secret = self._get_client_credentials(
                    token.client_id
                )

                async with httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT_SECONDS
                ) as http_client:
                    await http_client.post(
                        self._revocation_endpoint,
                        data={"token": token.token},
                        auth=(actual_client_id, actual_client_secret),
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

            # Log the incoming request (with sensitive data redacted)
            redacted_form = {
                k: (
                    str(v)[:8] + "..."
                    if k in {"code", "code_verifier", "client_secret", "refresh_token"}
                    and v
                    else str(v)
                )
                for k, v in form_data.items()
            }
            logger.debug("Proxy token request form data: %s", redacted_form)

            # Extract client_id to determine which credentials to use
            original_client_id = str(form_data.get("client_id", self._client_id))
            actual_client_id, actual_client_secret = self._get_client_credentials(
                original_client_id
            )

            # Build the upstream request data
            upstream_data = {
                "client_id": actual_client_id,
                "client_secret": actual_client_secret,
            }

            # Forward all relevant form fields
            for key, value in form_data.items():
                if key not in {
                    "client_id",
                    "client_secret",
                }:  # Don't override our credentials
                    upstream_data[key] = str(value)

            # Log outgoing request (with sensitive data redacted)
            redacted_upstream = {
                k: (
                    "***"
                    if k == "client_secret"
                    else (
                        str(v)[:8] + "..."
                        if k in {"code", "code_verifier", "refresh_token"}
                        else str(v)
                    )
                )
                for k, v in upstream_data.items()
            }
            logger.debug(
                "Forwarding proxy token request to upstream: %s", redacted_upstream
            )

            # Make the request to upstream server
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
                try:
                    response = await http_client.post(
                        self._token_endpoint,
                        data=upstream_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

                    logger.debug(
                        "Upstream proxy token response: status=%d, body_preview=%s",
                        response.status_code,
                        response.text[:200]
                        + ("..." if len(response.text) > 200 else ""),
                    )

                    # Return the upstream response directly
                    if response.status_code >= 400:
                        logger.warning(
                            "Upstream token request failed: %d - %s",
                            response.status_code,
                            response.text[:500],
                        )
                        # Forward the error response
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

                    # Success - forward the token response
                    token_data = response.json()

                    # Store tokens locally for tracking (if this is an authorization_code grant)
                    if (
                        upstream_data.get("grant_type") == "authorization_code"
                        and "access_token" in token_data
                    ):
                        self._store_tokens_from_response(token_data, actual_client_id)

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

                    # Maintain token relationships
                    self._access_to_refresh[access_token_value] = refresh_token_value
                    self._refresh_to_access[refresh_token_value] = access_token_value

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
                # Keep all other routes unchanged
                custom_routes.append(route)

        logger.info(
            "Customized OAuth routes for proxy behavior (replaced token endpoint)"
        )
        return custom_routes
