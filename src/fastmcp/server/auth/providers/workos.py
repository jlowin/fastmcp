"""WorkOS AuthKit provider for FastMCP.

This provider implements WorkOS AuthKit integration using static credentials.
Unlike the generic OAuthProxy, this provider is specifically designed for
WorkOS AuthKit's expected integration pattern.

Key features:
- Static client credentials (no DCR required)
- JWT token verification using WorkOS JWKS
- Simplified OAuth flow optimized for WorkOS
- Production-ready configuration
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.auth.settings import (
    ClientRegistrationOptions,
    RevocationOptions,
)
from pydantic import AnyHttpUrl

from fastmcp.server.auth.providers.proxy import OAuthProxy
from fastmcp.server.auth.verifiers import JWTVerifier

if TYPE_CHECKING:
    from fastmcp.server.auth.auth import TokenVerifier


class WorkOSAuthProvider(OAuthProxy):
    """WorkOS AuthKit authentication provider.

    This provider implements WorkOS AuthKit integration using static client
    credentials. It's designed specifically for WorkOS's expected OAuth flow
    pattern and provides a simpler alternative to the generic OAuthProxy for
    WorkOS integrations.

    Example:
        ```python
        from fastmcp.server.auth.providers.workos import WorkOSAuthProvider

        # Create WorkOS auth provider (JWT verifier created automatically)
        workos_auth = WorkOSAuthProvider(
            workos_domain="https://your-workos-domain.authkit.app",
            client_id="your_workos_client_id",
            client_secret="your_workos_client_secret",
            issuer_url="https://your-fastmcp-server.com",
        )

        # Use with FastMCP
        mcp = FastMCP("My App", auth=workos_auth)
        ```
    """

    def __init__(
        self,
        *,
        workos_domain: str,
        client_id: str,
        client_secret: str,
        token_verifier: TokenVerifier | None = None,
        issuer_url: AnyHttpUrl | str,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
    ):
        """Initialize WorkOS AuthKit provider.

        Args:
            workos_domain: Your WorkOS AuthKit domain (e.g., "https://your-app.authkit.app")
            client_id: WorkOS OAuth client ID
            client_secret: WorkOS OAuth client secret
            token_verifier: Optional token verifier. If None, creates default JWTVerifier for WorkOS
            issuer_url: Public URL of this FastMCP server
            service_documentation_url: Optional service documentation URL
            client_registration_options: Optional client registration settings
            revocation_options: Optional token revocation settings
        """
        workos_domain = workos_domain.rstrip("/")

        # Create default JWT verifier if none provided
        if token_verifier is None:
            token_verifier = JWTVerifier(
                jwks_uri=f"{workos_domain}/oauth2/jwks",
                issuer=workos_domain,
                algorithm="RS256",
                required_scopes=None,  # WorkOS doesn't include scope claims
            )

        # Initialize OAuthProxy with WorkOS endpoints (static credentials only)
        super().__init__(
            authorization_endpoint=f"{workos_domain}/oauth2/authorize",
            token_endpoint=f"{workos_domain}/oauth2/token",
            revocation_endpoint=f"{workos_domain}/oauth2/revoke",
            # No registration_endpoint = DCR disabled (static credentials only)
            client_id=client_id,
            client_secret=client_secret,
            token_verifier=token_verifier,
            issuer_url=issuer_url,
            service_documentation_url=service_documentation_url,
            client_registration_options=client_registration_options,
            revocation_options=revocation_options,
        )
