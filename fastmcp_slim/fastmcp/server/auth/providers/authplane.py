"""AuthPlane authentication provider for FastMCP."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pydantic import AnyHttpUrl

from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.utilities.auth import parse_scopes
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class AuthPlaneAuthProvider(RemoteAuthProvider):
    """AuthPlane authentication provider using JWT verification.

    This provider integrates AuthPlane (https://github.com/AuthPlane/authserver),
    an open-source, self-hosted OAuth 2.1 authorization server for MCP.

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.authplane import AuthPlaneAuthProvider

        auth = AuthPlaneAuthProvider(
            server_url="https://auth.example.com",
            base_url="https://my-mcp-server.example.com",
        )

        mcp = FastMCP("My App", auth=auth)
        ```
    """

    def __init__(
        self,
        *,
        server_url: AnyHttpUrl | str,
        base_url: AnyHttpUrl | str,
        required_scopes: list[str] | str | None = None,
        audience: str | list[str] | None = None,
        token_verifier: TokenVerifier | None = None,
    ):
        """Initialize the AuthPlane auth provider.

        Args:
            server_url: AuthPlane server URL (e.g., "https://auth.example.com")
            base_url: Public URL of this FastMCP server
            required_scopes: Scopes to require on incoming tokens. Defaults to
                ["openid"], which ensures the `sub` claim (user identifier) is
                present in the access token. Override to require additional scopes.
            audience: Optional audience(s) for JWT validation. Recommended for production.
            token_verifier: Optional custom token verifier. Defaults to a JWTVerifier
                configured for AuthPlane's JWKS endpoint and issuer.
        """
        self.server_url = str(server_url).rstrip("/")
        parsed_scopes = (
            parse_scopes(required_scopes) if required_scopes is not None else ["openid"]
        )

        if token_verifier is None:
            # AuthPlane follows standard OAuth 2.1, JWKS at /.well-known/jwks.json
            token_verifier = JWTVerifier(
                jwks_uri=f"{self.server_url}/.well-known/jwks.json",
                issuer=self.server_url,
                algorithm="RS256",
                required_scopes=parsed_scopes,
                audience=audience,
            )

        super().__init__(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl(self.server_url)],
            base_url=AnyHttpUrl(str(base_url).rstrip("/")),
        )
