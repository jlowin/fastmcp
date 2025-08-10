"""OAuth Proxy Provider for FastMCP.

This provider acts as a transparent proxy to an upstream OAuth Authorization Server,
handling Dynamic Client Registration locally while forwarding all other OAuth flows.
This enables authentication with upstream providers that don't support DCR or have
restricted client registration policies.

Key features:
- Proxies authorization and token endpoints to upstream server
- Implements local Dynamic Client Registration with fixed upstream credentials
- Validates tokens using upstream JWKS
- Maintains minimal local state for bookkeeping
- Enhanced logging with request correlation

This implementation is based on the OAuth 2.1 specification and is designed for
production use with enterprise identity providers.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
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
    - Client registration is handled locally with fixed upstream credentials
    - Authorization flows redirect to the upstream server
    - Token exchange is forwarded to the upstream server
    - Token validation uses upstream JWKS
    - Minimal local state is maintained for bookkeeping

    This approach allows FastMCP to work with enterprise identity providers
    that don't support Dynamic Client Registration or have restricted policies.
    """

    def __init__(
        self,
        *,
        # Upstream server configuration
        upstream_authorization_endpoint: str,
        upstream_token_endpoint: str,
        upstream_client_id: str,
        upstream_client_secret: str,
        upstream_revocation_endpoint: str | None = None,
        # Token validation
        token_verifier: TokenVerifier,
        # FastMCP server configuration
        base_url: AnyHttpUrl | str,
        issuer_url: AnyHttpUrl | str | None = None,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
        resource_server_url: AnyHttpUrl | str | None = None,
    ):
        """Initialize the OAuth proxy provider.

        Args:
            upstream_authorization_endpoint: URL of upstream authorization endpoint
            upstream_token_endpoint: URL of upstream token endpoint
            upstream_client_id: Client ID registered with upstream server
            upstream_client_secret: Client secret for upstream server
            upstream_revocation_endpoint: Optional upstream revocation endpoint
            token_verifier: Token verifier for validating access tokens
            base_url: Public URL of this FastMCP server
            issuer_url: Issuer URL for OAuth metadata (defaults to base_url)
            service_documentation_url: Optional service documentation URL
            client_registration_options: Local client registration options
            revocation_options: Token revocation options
            resource_server_url: Resource server URL (defaults to base_url)
        """
        # Enable DCR by default since we implement it locally
        if client_registration_options is None:
            client_registration_options = ClientRegistrationOptions(enabled=True)

        # Set up revocation if upstream endpoint provided
        if upstream_revocation_endpoint and revocation_options is None:
            revocation_options = RevocationOptions(enabled=True)

        super().__init__(
            base_url=base_url,
            issuer_url=issuer_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
            required_scopes=token_verifier.required_scopes,
            resource_server_url=resource_server_url,
        )

        # Store upstream configuration
        self._upstream_authorization_endpoint = upstream_authorization_endpoint
        self._upstream_token_endpoint = upstream_token_endpoint
        self._upstream_client_id = upstream_client_id
        self._upstream_client_secret = SecretStr(upstream_client_secret)
        self._upstream_revocation_endpoint = upstream_revocation_endpoint

        # Local state for DCR and token bookkeeping
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

        # Token relation mappings for cleanup
        self._access_to_refresh: dict[str, str] = {}
        self._refresh_to_access: dict[str, str] = {}

        # Use the provided token validator
        self._token_validator = token_verifier

        logger.info(
            "Initialized OAuth proxy provider with upstream server %s",
            self._upstream_authorization_endpoint,
        )

    # -------------------------------------------------------------------------
    # Client Registration (Local Implementation)
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
                from fastmcp.server.dependencies import (
                    get_http_request,  # local import to avoid circular dependency
                )
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
    ) -> None:
        """Register a client locally using fixed upstream credentials.

        This implementation always uses the upstream client_id and client_secret
        regardless of what the client requests. It modifies the client_info object
        in place since the MCP framework ignores return values.
        
        This ensures all clients use the same credentials that are registered
        with the upstream server.
        """
        # Always use the upstream credentials
        upstream_id = self._upstream_client_id
        upstream_secret = self._upstream_client_secret.get_secret_value()

        # Modify the client_info object in place (framework ignores return values)
        client_info.client_id = upstream_id
        client_info.client_secret = upstream_secret
        client_info.token_endpoint_auth_method = "none"
        
        # Ensure correct grant types
        if not client_info.grant_types:
            client_info.grant_types = ["authorization_code", "refresh_token"]

        # Store the client registration using the upstream ID
        self._clients[upstream_id] = client_info

        logger.info(
            "Registered client %s with %d redirect URIs",
            upstream_id,
            len(client_info.redirect_uris),
        )

    # -------------------------------------------------------------------------
    # Authorization Flow (Proxy to Upstream)
    # -------------------------------------------------------------------------

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
        # Build query parameters for upstream authorization request
        query_params: dict[str, Any] = {
            "response_type": "code",
            "client_id": self._upstream_client_id,
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
        upstream_url = (
            f"{self._upstream_authorization_endpoint}?{urlencode(query_params)}"
        )

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

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Exchange authorization code for tokens with upstream server using authlib.

        Uses authlib's AsyncOAuth2Client to handle the token exchange, which
        automatically handles both JSON and form-encoded responses, PKCE, and
        other OAuth complexities.
        """
        # Extract additional parameters from the current request
        code_verifier = None
        redirect_uri = str(authorization_code.redirect_uri)
        
        try:
            from fastmcp.server.dependencies import (
                get_http_request,  # local import to avoid circular dependency
            )
            req = get_http_request()
            if req.method == "POST":
                form = await req.form()

                # Extract PKCE code_verifier if present
                if "code_verifier" in form:
                    code_verifier = str(form["code_verifier"])
                
                # Extract redirect_uri if present
                if "redirect_uri" in form:
                    redirect_uri = str(form["redirect_uri"])

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

        except Exception as e:
            logger.warning("Could not extract form data from request: %s", e)

        # Use authlib's AsyncOAuth2Client for token exchange
        oauth_client = AsyncOAuth2Client(
            client_id=self._upstream_client_id,
            client_secret=self._upstream_client_secret.get_secret_value(),
            timeout=HTTP_TIMEOUT_SECONDS,
        )

        try:
            logger.debug("Using authlib to fetch token from upstream")
            
            # Let authlib handle the token exchange - it automatically handles
            # JSON/form-encoded responses, PKCE, error handling, etc.
            token_response = await oauth_client.fetch_token(
                url=self._upstream_token_endpoint,
                code=authorization_code.code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )

            logger.info(
                "Successfully exchanged authorization code via authlib (client: %s)",
                client.client_id,
            )

        except Exception as e:
            logger.error("Authlib token exchange failed: %s", e)
            raise TokenError(
                "invalid_grant", f"Upstream token exchange failed: {e}"
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
        """Exchange refresh token for new access token using authlib."""
        
        # Use authlib's AsyncOAuth2Client for refresh token exchange
        oauth_client = AsyncOAuth2Client(
            client_id=self._upstream_client_id,
            client_secret=self._upstream_client_secret.get_secret_value(),
            timeout=HTTP_TIMEOUT_SECONDS,
        )

        try:
            logger.debug("Using authlib to refresh token from upstream")
            
            # Let authlib handle the refresh token exchange
            token_response = await oauth_client.refresh_token(
                url=self._upstream_token_endpoint,
                refresh_token=refresh_token.token,
                scope=" ".join(scopes) if scopes else None,
            )

            logger.info(
                "Successfully refreshed access token via authlib (client: %s)", 
                client.client_id
            )

        except Exception as e:
            logger.error("Authlib refresh token exchange failed: %s", e)
            raise TokenError(
                "invalid_grant", f"Upstream refresh token exchange failed: {e}"
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
        if self._upstream_revocation_endpoint:
            try:
                async with httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT_SECONDS
                ) as http_client:
                    await http_client.post(
                        self._upstream_revocation_endpoint,
                        data={"token": token.token},
                        auth=(
                            self._upstream_client_id,
                            self._upstream_client_secret.get_secret_value(),
                        ),
                    )
                    logger.info("Successfully revoked token with upstream server")
            except Exception as e:
                logger.warning("Failed to revoke token with upstream server: %s", e)
        else:
            logger.debug("No upstream revocation endpoint configured")

        logger.info("Token revoked successfully")

    # -------------------------------------------------------------------------
    # Custom Route Handling
    # -------------------------------------------------------------------------

    async def _handle_proxy_token_request(self, request: Request) -> JSONResponse:
        """Custom token endpoint using authlib for upstream requests.

        This handler uses authlib's OAuth2Client to forward token requests to the
        upstream OAuth server, automatically handling response format differences.
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

            # Create authlib OAuth2 client
            oauth_client = AsyncOAuth2Client(
                client_id=self._upstream_client_id,
                client_secret=self._upstream_client_secret.get_secret_value(),
                timeout=HTTP_TIMEOUT_SECONDS,
            )

            grant_type = str(form_data.get("grant_type", ""))
            
            if grant_type == "authorization_code":
                # Authorization code grant
                try:
                    token_data = await oauth_client.fetch_token(
                        url=self._upstream_token_endpoint,
                        code=str(form_data.get("code", "")),
                        redirect_uri=str(form_data.get("redirect_uri", "")),
                        code_verifier=str(form_data.get("code_verifier")) if "code_verifier" in form_data else None,
                    )
                    
                    # Store tokens locally for tracking
                    if "access_token" in token_data:
                        self._store_tokens_from_response(token_data)
                        
                    logger.info("Successfully proxied authorization code exchange via authlib")
                    
                except Exception as e:
                    logger.error("Authlib authorization code exchange failed: %s", e)
                    return JSONResponse(
                        content={
                            "error": "invalid_grant",
                            "error_description": f"Authorization code exchange failed: {e}",
                        },
                        status_code=400,
                    )
                    
            elif grant_type == "refresh_token":
                # Refresh token grant
                try:
                    token_data = await oauth_client.refresh_token(
                        url=self._upstream_token_endpoint,
                        refresh_token=str(form_data.get("refresh_token", "")),
                        scope=str(form_data.get("scope")) if "scope" in form_data else None,
                    )
                    
                    logger.info("Successfully proxied refresh token exchange via authlib")
                    
                except Exception as e:
                    logger.error("Authlib refresh token exchange failed: %s", e)
                    return JSONResponse(
                        content={
                            "error": "invalid_grant",
                            "error_description": f"Refresh token exchange failed: {e}",
                        },
                        status_code=400,
                    )
            else:
                # Unsupported grant type
                logger.error("Unsupported grant type: %s", grant_type)
                return JSONResponse(
                    content={
                        "error": "unsupported_grant_type",
                        "error_description": f"Grant type '{grant_type}' not supported by proxy",
                    },
                    status_code=400,
                )

            return JSONResponse(content=token_data)

        except Exception as e:
            logger.error("Error in proxy token handler: %s", e, exc_info=True)
            return JSONResponse(
                content={
                    "error": "server_error",
                    "error_description": "Internal server error",
                },
                status_code=500,
            )

    def _store_tokens_from_response(self, token_data: dict[str, Any]) -> None:
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
                    client_id=self._upstream_client_id,
                    scopes=[],  # Will be determined by token validation
                    expires_at=expires_at,
                )
                self._access_tokens[access_token_value] = access_token

                if refresh_token_value:
                    refresh_token = RefreshToken(
                        token=refresh_token_value,
                        client_id=self._upstream_client_id,
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

    def get_routes(self) -> list[Route]:
        """Get OAuth routes with custom proxy token handler.

        This method creates standard OAuth routes and replaces the token endpoint
        with our proxy handler that forwards requests to the upstream OAuth server.
        """
        # Get standard OAuth routes from parent class
        routes = super().get_routes()
        custom_routes = []
        token_route_found = False

        logger.info(f"get_routes called - replacing token endpoint in {len(routes)} routes")
        
        for i, route in enumerate(routes):
            logger.debug(f"Route {i}: {route} - path: {getattr(route, 'path', 'N/A')}, methods: {getattr(route, 'methods', 'N/A')}")
            
            # Replace the token endpoint with our proxy handler
            if (
                isinstance(route, Route)
                and route.path == "/token"
                and route.methods is not None
                and "POST" in route.methods
            ):
                logger.info("🔄 REPLACING standard token endpoint with proxy handler")
                token_route_found = True
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

        if not token_route_found:
            logger.warning("⚠️  No /token POST route found to replace! Adding proxy handler.")
            custom_routes.append(
                Route(
                    path="/token",
                    endpoint=self._handle_proxy_token_request,
                    methods=["POST"],
                )
            )

        logger.info(
            f"✅ OAuth routes customized: replaced={token_route_found}, total routes={len(custom_routes)}"
        )
        return custom_routes