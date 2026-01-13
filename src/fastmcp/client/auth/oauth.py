from __future__ import annotations

import time
import webbrowser
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any

import anyio
import httpx
from key_value.aio.adapters.pydantic import PydanticAdapter
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.memory import MemoryStore
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.auth.utils import is_valid_client_metadata_url
from mcp.shared._httpx_utils import McpHttpClientFactory
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyHttpUrl
from typing_extensions import override
from uvicorn.server import Server

from fastmcp.client.oauth_callback import (
    OAuthCallbackResult,
    create_oauth_callback_server,
)
from fastmcp.utilities.http import find_available_port
from fastmcp.utilities.logging import get_logger

__all__ = ["OAuth"]

logger = get_logger(__name__)


class ClientNotFoundError(Exception):
    """Raised when OAuth client credentials are not found on the server."""


async def check_if_auth_required(
    mcp_url: str, httpx_kwargs: dict[str, Any] | None = None
) -> bool:
    """
    Check if the MCP endpoint requires authentication by making a test request.

    Returns:
        True if auth appears to be required, False otherwise
    """
    async with httpx.AsyncClient(**(httpx_kwargs or {})) as client:
        try:
            # Try a simple request to the endpoint
            response = await client.get(mcp_url, timeout=5.0)

            # If we get 401/403, auth is likely required
            if response.status_code in (401, 403):
                return True

            # Check for WWW-Authenticate header
            if "WWW-Authenticate" in response.headers:  # noqa: SIM103
                return True

            # If we get a successful response, auth may not be required
            return False

        except httpx.RequestError:
            # If we can't connect, assume auth might be required
            return True


class TokenStorageAdapter(TokenStorage):
    _server_url: str
    _key_value_store: AsyncKeyValue
    _storage_oauth_token: PydanticAdapter[OAuthToken]
    _storage_client_info: PydanticAdapter[OAuthClientInformationFull]

    def __init__(self, async_key_value: AsyncKeyValue, server_url: str):
        self._server_url = server_url
        self._key_value_store = async_key_value
        self._storage_oauth_token = PydanticAdapter[OAuthToken](
            default_collection="mcp-oauth-token",
            key_value=async_key_value,
            pydantic_model=OAuthToken,
            raise_on_validation_error=True,
        )
        self._storage_client_info = PydanticAdapter[OAuthClientInformationFull](
            default_collection="mcp-oauth-client-info",
            key_value=async_key_value,
            pydantic_model=OAuthClientInformationFull,
            raise_on_validation_error=True,
        )

    def _get_token_cache_key(self) -> str:
        return f"{self._server_url}/tokens"

    def _get_client_info_cache_key(self) -> str:
        return f"{self._server_url}/client_info"

    async def clear(self) -> None:
        await self._storage_oauth_token.delete(key=self._get_token_cache_key())
        await self._storage_client_info.delete(key=self._get_client_info_cache_key())

    @override
    async def get_tokens(self) -> OAuthToken | None:
        return await self._storage_oauth_token.get(key=self._get_token_cache_key())

    @override
    async def set_tokens(self, tokens: OAuthToken) -> None:
        # Don't set TTL based on access token expiry - the refresh token may be
        # valid much longer. Use 1 year as a reasonable upper bound; the OAuth
        # provider handles actual token expiry/refresh logic.
        await self._storage_oauth_token.put(
            key=self._get_token_cache_key(),
            value=tokens,
            ttl=60 * 60 * 24 * 365,  # 1 year
        )

    @override
    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return await self._storage_client_info.get(
            key=self._get_client_info_cache_key()
        )

    @override
    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        ttl: int | None = None

        if client_info.client_secret_expires_at:
            ttl = client_info.client_secret_expires_at - int(time.time())

        await self._storage_client_info.put(
            key=self._get_client_info_cache_key(),
            value=client_info,
            ttl=ttl,
        )


class OAuth:
    """
    OAuth configuration for MCP client authentication.

    This is a configuration object that specifies how OAuth authentication should
    work. The actual authentication provider is created by the transport when
    the client connects.

    Supports two registration modes:
    - Dynamic Client Registration (DCR): Traditional OAuth where the client
      registers with the server and receives a client_id/secret. This is the
      default when no client_metadata_url is provided.
    - Client ID Metadata Document (CIMD): URL-based identity where the client
      hosts a metadata document and uses that URL as its client_id. This is
      recommended for production clients as it provides verifiable identity.

    Example:
        # DCR (quick scripts, testing)
        client = Client("https://mcp.example.com", auth=OAuth())

        # CIMD (recommended for production)
        client = Client(
            "https://mcp.example.com",
            auth=OAuth(client_metadata_url="https://myapp.com/oauth/client.json"),
        )
    """

    def __init__(
        self,
        scopes: str | list[str] | None = None,
        client_name: str = "FastMCP Client",
        client_metadata_url: str | None = None,
        token_storage: AsyncKeyValue | None = None,
        additional_client_metadata: dict[str, Any] | None = None,
        callback_port: int | None = None,
        httpx_client_factory: McpHttpClientFactory | None = None,
    ):
        """
        Initialize OAuth configuration.

        Args:
            scopes: OAuth scopes to request. Can be a space-separated string
                or a list of strings.
            client_name: Name for this client during registration (DCR only).
            client_metadata_url: URL-based client ID (CIMD). When provided and
                the server advertises CIMD support, this URL is used as the
                client_id instead of Dynamic Client Registration. Must be an
                HTTPS URL with a non-root path (e.g., "https://myapp.com/oauth/client.json").
            token_storage: An AsyncKeyValue-compatible token store. Tokens are
                stored in memory if not provided (with a warning).
            additional_client_metadata: Extra fields for OAuthClientMetadata.
            callback_port: Fixed port for OAuth callback (default: random available port).
            httpx_client_factory: Factory for creating httpx clients.
        """
        # Validate client_metadata_url if provided
        if client_metadata_url is not None and not is_valid_client_metadata_url(
            client_metadata_url
        ):
            raise ValueError(
                f"client_metadata_url must be a valid HTTPS URL with a non-root pathname, "
                f"got: {client_metadata_url}"
            )

        self.scopes = scopes
        self.client_name = client_name
        self.client_metadata_url = client_metadata_url
        self.token_storage = token_storage
        self.additional_client_metadata = additional_client_metadata
        self.callback_port = callback_port
        self.httpx_client_factory = httpx_client_factory


class _OAuthSession(OAuthClientProvider):
    """
    Internal OAuth provider implementation.

    This is the actual httpx.Auth implementation that handles the OAuth flow.
    It is created by the transport from OAuth configuration values and the
    target MCP URL.

    Users should not instantiate this directly - use OAuth config with a transport.
    """

    def __init__(
        self,
        mcp_url: str,
        *,
        scopes: str | list[str] | None = None,
        client_name: str = "FastMCP Client",
        client_metadata_url: str | None = None,
        token_storage: AsyncKeyValue | None = None,
        additional_client_metadata: dict[str, Any] | None = None,
        callback_port: int | None = None,
        httpx_client_factory: McpHttpClientFactory | None = None,
    ):
        """
        Initialize OAuth session for a specific MCP server.

        Args:
            mcp_url: Full URL to the MCP endpoint.
            scopes: OAuth scopes to request.
            client_name: Name for this client during registration.
            client_metadata_url: URL-based client ID (CIMD).
            token_storage: Token storage backend.
            additional_client_metadata: Extra fields for OAuthClientMetadata.
            callback_port: Fixed port for OAuth callback.
            httpx_client_factory: Factory for creating httpx clients.
        """
        # Normalize the MCP URL (strip trailing slashes for consistency)
        mcp_url = mcp_url.rstrip("/")

        # Setup OAuth client
        self.httpx_client_factory = httpx_client_factory or httpx.AsyncClient
        self.redirect_port = callback_port or find_available_port()
        redirect_uri = f"http://localhost:{self.redirect_port}/callback"

        scopes_str: str
        if isinstance(scopes, list):
            scopes_str = " ".join(scopes)
        elif scopes is not None:
            scopes_str = str(scopes)
        else:
            scopes_str = ""

        client_metadata = OAuthClientMetadata(
            client_name=client_name,
            redirect_uris=[AnyHttpUrl(redirect_uri)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=scopes_str,
            **(additional_client_metadata or {}),
        )

        # Create server-specific token storage
        token_storage = token_storage or MemoryStore()

        if isinstance(token_storage, MemoryStore):
            from warnings import warn

            warn(
                message="Using in-memory token storage -- tokens will be lost when the client restarts. "
                + "For persistent storage across multiple MCP servers, provide an encrypted AsyncKeyValue backend. "
                + "See https://gofastmcp.com/clients/auth/oauth#token-storage for details.",
                stacklevel=4,
            )

        # Use full URL for token storage to properly separate tokens per MCP endpoint
        self.token_storage_adapter: TokenStorageAdapter = TokenStorageAdapter(
            async_key_value=token_storage, server_url=mcp_url
        )

        # Store full MCP URL for use in callback_handler display
        self.mcp_url = mcp_url

        # Initialize parent class with full URL for proper OAuth metadata discovery
        super().__init__(
            server_url=mcp_url,
            client_metadata=client_metadata,
            storage=self.token_storage_adapter,
            redirect_handler=self.redirect_handler,
            callback_handler=self.callback_handler,
            client_metadata_url=client_metadata_url,
        )

    async def _initialize(self) -> None:
        """Load stored tokens and client info, properly setting token expiry."""
        # Call parent's _initialize to load tokens and client info
        await super()._initialize()

        # If tokens were loaded and have expires_in, update the context's token_expiry_time
        if self.context.current_tokens and self.context.current_tokens.expires_in:
            self.context.update_token_expiry(self.context.current_tokens)

    async def redirect_handler(self, authorization_url: str) -> None:
        """Open browser for authorization, with pre-flight check for invalid client."""
        # Pre-flight check to detect invalid client_id before opening browser
        async with self.httpx_client_factory() as client:
            response = await client.get(authorization_url, follow_redirects=False)

            # Check for client not found error (400 typically means bad client_id)
            if response.status_code == 400:
                raise ClientNotFoundError(
                    "OAuth client not found - cached credentials may be stale"
                )

            # OAuth typically returns redirects, but some providers return 200 with HTML login pages
            if response.status_code not in (200, 302, 303, 307, 308):
                raise RuntimeError(
                    f"Unexpected authorization response: {response.status_code}"
                )

        logger.info(f"OAuth authorization URL: {authorization_url}")
        webbrowser.open(authorization_url)

    async def callback_handler(self) -> tuple[str, str | None]:
        """Handle OAuth callback and return (auth_code, state)."""
        # Create result container and event to capture the OAuth response
        result = OAuthCallbackResult()
        result_ready = anyio.Event()

        # Create server with result tracking
        server: Server = create_oauth_callback_server(
            port=self.redirect_port,
            server_url=self.mcp_url,
            result_container=result,
            result_ready=result_ready,
        )

        # Run server until response is received with timeout logic
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.serve)
            logger.info(
                f"🎧 OAuth callback server started on http://localhost:{self.redirect_port}"
            )

            TIMEOUT = 300.0  # 5 minute timeout
            try:
                with anyio.fail_after(TIMEOUT):
                    await result_ready.wait()
                    if result.error:
                        raise result.error
                    return result.code, result.state  # type: ignore
            except TimeoutError as e:
                raise TimeoutError(
                    f"OAuth callback timed out after {TIMEOUT} seconds"
                ) from e
            finally:
                server.should_exit = True
                await anyio.sleep(0.1)  # Allow server to shut down gracefully
                tg.cancel_scope.cancel()

        raise RuntimeError("OAuth callback handler could not be started")

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """HTTPX auth flow with automatic retry on stale cached credentials.

        If the OAuth flow fails due to invalid/stale client credentials,
        clears the cache and retries once with fresh registration.
        """
        try:
            # First attempt with potentially cached credentials
            async with aclosing(super().async_auth_flow(request)) as gen:
                response = None
                while True:
                    try:
                        # First iteration sends None, subsequent iterations send response
                        yielded_request = await gen.asend(response)  # ty: ignore[invalid-argument-type]
                        response = yield yielded_request
                    except StopAsyncIteration:
                        break

        except ClientNotFoundError:
            logger.debug(
                "OAuth client not found on server, clearing cache and retrying..."
            )
            # Clear cached state and retry once
            self._initialized = False
            await self.token_storage_adapter.clear()

            # Retry with fresh registration
            async with aclosing(super().async_auth_flow(request)) as gen:
                response = None
                while True:
                    try:
                        yielded_request = await gen.asend(response)  # ty: ignore[invalid-argument-type]
                        response = yield yielded_request
                    except StopAsyncIteration:
                        break
