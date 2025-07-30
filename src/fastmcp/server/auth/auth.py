from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.server.auth.provider import (
    TokenVerifier as TokenVerifierProtocol,
)
from mcp.server.auth.settings import (
    ClientRegistrationOptions,
    RevocationOptions,
)
from pydantic import AnyHttpUrl

if TYPE_CHECKING:
    from starlette.routing import BaseRoute


class TokenVerifier(TokenVerifierProtocol):
    """Base class for token verifiers (Resource Servers)."""

    def __init__(
        self,
        resource_server_url: AnyHttpUrl | str | None = None,
        required_scopes: list[str] | None = None,
    ):
        """
        Initialize the token verifier.

        Args:
            resource_server_url: The URL of this resource server (for RFC 8707 resource indicators)
            required_scopes: Scopes that are required for all requests
        """
        self.resource_server_url: AnyHttpUrl | None
        if resource_server_url is None:
            self.resource_server_url = None
        elif isinstance(resource_server_url, str):
            self.resource_server_url = AnyHttpUrl(resource_server_url)
        else:
            self.resource_server_url = resource_server_url
        self.required_scopes = required_scopes or []

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return access info if valid."""
        raise NotImplementedError("Subclasses must implement verify_token")


class OAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(
        self,
        issuer_url: AnyHttpUrl | str,
        service_documentation_url: AnyHttpUrl | str | None = None,
        client_registration_options: ClientRegistrationOptions | None = None,
        revocation_options: RevocationOptions | None = None,
        required_scopes: list[str] | None = None,
        resource_server_url: AnyHttpUrl | str | None = None,
    ):
        """
        Initialize the OAuth provider.

        Args:
            issuer_url: The URL of the OAuth issuer.
            service_documentation_url: The URL of the service documentation.
            client_registration_options: The client registration options.
            revocation_options: The revocation options.
            required_scopes: Scopes that are required for all requests.
        """
        super().__init__()
        if isinstance(issuer_url, str):
            issuer_url = AnyHttpUrl(issuer_url)
        if isinstance(service_documentation_url, str):
            service_documentation_url = AnyHttpUrl(service_documentation_url)

        self.issuer_url = issuer_url
        self.service_documentation_url = service_documentation_url
        self.client_registration_options = client_registration_options
        self.revocation_options = revocation_options
        self.required_scopes = required_scopes

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify a bearer token and return access info if valid.

        This method implements the TokenVerifier protocol by delegating
        to our existing load_access_token method.

        Args:
            token: The token string to validate

        Returns:
            AccessToken object if valid, None if invalid or expired
        """
        return await self.load_access_token(token)

    def customize_auth_routes(self, routes: list[BaseRoute]) -> list[BaseRoute]:
        """Customize OAuth authentication routes after standard creation.

        This method allows providers to modify the standard OAuth routes
        returned by create_auth_routes. The default implementation returns
        the routes unchanged.

        Args:
            routes: List of standard OAuth routes from create_auth_routes

        Returns:
            List of routes (potentially modified)
        """
        return routes
