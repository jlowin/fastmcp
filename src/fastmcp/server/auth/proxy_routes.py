from __future__ import annotations

"""Utility to create auth routes that use ProxyTokenHandler instead of the
standard TokenHandler.  This is injected at runtime by TransparentOAuthProxyProvider
so that the proxy-friendly logic is only active when necessary.
"""

from typing import Any

from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.auth.routes import (
    create_auth_routes as _orig_create_auth_routes,
    TOKEN_PATH,
    cors_middleware,
)
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import OAuthAuthorizationServerProvider
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl

from .proxy_token_handler import ProxyTokenHandler


def create_proxy_auth_routes(
    *,
    provider: OAuthAuthorizationServerProvider[Any, Any, Any],
    issuer_url: AnyHttpUrl,
    service_documentation_url: AnyHttpUrl | None = None,
    client_registration_options: ClientRegistrationOptions | None = None,
    revocation_options: RevocationOptions | None = None,
):
    """Drop-in replacement for mcp.server.auth.routes.create_auth_routes()."""

    # First build the default route list
    routes = _orig_create_auth_routes(
        provider=provider,
        issuer_url=issuer_url,
        service_documentation_url=service_documentation_url,
        client_registration_options=client_registration_options,
        revocation_options=revocation_options,
    )

    # Build our replacement /token route
    client_authenticator = ClientAuthenticator(provider)
    proxy_handler = ProxyTokenHandler(provider, client_authenticator).handle

    proxy_route = Route(
        TOKEN_PATH,
        endpoint=cors_middleware(proxy_handler, ["POST", "OPTIONS"]),
        methods=["POST", "OPTIONS"],
    )

    # Remove the original /token definition in a single pass
    new_routes: list[Route] = [
        r for r in routes if not (isinstance(r, Route) and r.path == TOKEN_PATH)
    ]
    new_routes.append(proxy_route)

    # Add ".well-known/oauth-protected-resource" metadata route at the root.
    async def protected_resource_metadata(request: Request):  # noqa: D401
        """Return OAuth protected-resource metadata.

        Mirrors RFC 8414 Section 5.  Clients use this endpoint to discover the
        issuer and the corresponding Authorization Server metadata served by
        FastMCP when operating as a transparent OAuth proxy.
        """
        base = str(request.url.replace(path="")).rstrip("/")
        # Prefer the public jwks_uri property; fall back to getattr for
        # compatibility with custom provider subclasses.
        jwks_uri = getattr(provider, "jwks_uri", None) or ""
        return JSONResponse(
            {
                "issuer": base,
                "authorization_server": f"{base}/.well-known/oauth-authorization-server",
                "jwks_uri": jwks_uri,
            }
        )

    # Prepend the route so that it has high precedence (mirrors behaviour in example)
    new_routes.insert(0, Route("/.well-known/oauth-protected-resource", protected_resource_metadata, methods=["GET"]))

    return new_routes 