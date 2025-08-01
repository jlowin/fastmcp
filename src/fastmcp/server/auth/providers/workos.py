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

import httpx
from mcp.server.auth.provider import (
    AccessToken,
)
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from fastmcp.server.auth.auth import AuthProvider, TokenVerifier
from fastmcp.server.auth.verifiers import JWTVerifier
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class AuthKitProvider(AuthProvider):
    """WorkOS AuthKit metadata provider for DCR (Dynamic Client Registration).

    This provider implements WorkOS AuthKit integration using metadata forwarding
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

    3. Use compatible authentication methods:
       - "none" (public clients with PKCE) - RECOMMENDED for most use cases
       - "client_secret_basic" (confidential clients with HTTP Basic auth)
       - DO NOT use "client_secret_post" - WorkOS will reject it

    Example:
        ```python
        from fastmcp.server.auth.providers.workos import WorkOSMetadataProvider

        # Create WorkOS metadata provider (JWT verifier created automatically)
        workos_auth = WorkOSMetadataProvider(
            workos_domain="https://your-workos-domain.authkit.app",
            base_url="https://your-fastmcp-server.com",
        )

        # Use with FastMCP
        mcp = FastMCP("My App", auth=workos_auth)
        ```
    """

    def __init__(
        self,
        *,
        workos_domain: str,
        token_verifier: TokenVerifier | None = None,
        base_url: AnyHttpUrl | str,
    ):
        """Initialize WorkOS metadata provider.

        Args:
            workos_domain: Your WorkOS AuthKit domain (e.g., "https://your-app.authkit.app")
            token_verifier: Optional token verifier. If None, creates JWT verifier for WorkOS
            base_url: Public URL of this FastMCP server
        """
        super().__init__()

        self.workos_domain = workos_domain.rstrip("/")
        self.base_url = base_url if isinstance(base_url, str) else str(base_url)

        # Create default JWT verifier if none provided (WorkOS recommended approach)
        if token_verifier is None:
            token_verifier = JWTVerifier(
                jwks_uri=f"{self.workos_domain}/oauth2/jwks",
                issuer=self.workos_domain,
                algorithm="RS256",
                required_scopes=None,  # WorkOS doesn't include scope claims
            )

        self.token_verifier = token_verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a WorkOS token using the configured token verifier."""
        return await self.token_verifier.verify_token(token)

    def customize_auth_routes(self, routes: list[BaseRoute]) -> list[BaseRoute]:
        """Add WorkOS metadata endpoints.

        This adds:
        - /.well-known/oauth-authorization-server (forwards WorkOS metadata)
        - /.well-known/oauth-protected-resource (returns FastMCP resource info)
        """

        async def oauth_authorization_server_metadata(request):
            """Forward WorkOS OAuth authorization server metadata with FastMCP customizations."""
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.workos_domain}/.well-known/oauth-authorization-server"
                    )
                    response.raise_for_status()
                    metadata = response.json()

                    # Customize metadata for FastMCP client compatibility
                    # WorkOS only supports "none" and "client_secret_basic", NOT "client_secret_post"
                    if "token_endpoint_auth_methods_supported" in metadata:
                        # Filter out unsupported methods and ensure proper order
                        auth_methods = metadata["token_endpoint_auth_methods_supported"]
                        # WorkOS typically returns ["none", "client_secret_post", "client_secret_basic"]
                        # but client_secret_post causes errors, so we filter it out
                        supported_methods = []
                        if "none" in auth_methods:
                            supported_methods.append("none")
                        if "client_secret_basic" in auth_methods:
                            supported_methods.append("client_secret_basic")
                        # Explicitly exclude client_secret_post as it's not actually supported
                        metadata["token_endpoint_auth_methods_supported"] = (
                            supported_methods
                        )
                    else:
                        # Default to WorkOS-compatible methods only
                        metadata["token_endpoint_auth_methods_supported"] = [
                            "none",
                            "client_secret_basic",
                        ]

                    return JSONResponse(metadata)
            except Exception as e:
                return JSONResponse(
                    {
                        "error": "server_error",
                        "error_description": f"Failed to fetch WorkOS metadata: {e}",
                    },
                    status_code=500,
                )

        async def oauth_protected_resource_metadata(request):
            """Return FastMCP resource server metadata."""
            return JSONResponse(
                {
                    "resource": self.base_url,
                    "authorization_servers": [self.workos_domain],
                    "bearer_methods_supported": ["header"],
                    # "resource_documentation": f"{self.base_url}/docs"
                    # if hasattr(self, "service_documentation_url")
                    # else None,
                }
            )

        # Add ONLY metadata routes - let WorkOS handle DCR directly
        custom_routes = list(routes)  # Copy existing routes
        custom_routes.extend(
            [
                Route(
                    "/.well-known/oauth-authorization-server",
                    endpoint=oauth_authorization_server_metadata,
                    methods=["GET"],
                ),
                Route(
                    "/.well-known/oauth-protected-resource",
                    endpoint=oauth_protected_resource_metadata,
                    methods=["GET"],
                ),
            ]
        )

        return custom_routes
