"""MCPBundles Connect Auth provider for FastMCP."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

import httpx2
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse
from starlette.routing import Route

from fastmcp.server.auth import AccessToken, RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.utilities.auth import parse_scopes
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

INTEGRATION_DOC_URL = "https://www.mcpbundles.com/docs/integrations/mcp-connect-auth"
DEFAULT_PUBLIC_CONFIG_BASE_URL = "https://api.mcpbundles.com"
DEFAULT_HTTP_TIMEOUT = 10.0


def connect_auth_callback_identity(access_token: AccessToken) -> dict[str, Any]:
    """Build the canonical Connect Auth tool callback shape from a verified token.

    Matches the mcp-use ``get-user-info`` example: identity on ``user``, OAuth
    metadata on ``auth``. See the MCPBundles integration guide § Tool callback
    identity.
    """
    claims = access_token.claims
    organization_id = claims.get("organization_id")
    email = claims.get("email")
    roles_raw = claims.get("roles")
    roles: list[str] = []
    if isinstance(roles_raw, list):
        roles = [role for role in roles_raw if isinstance(role, str)]

    audience = claims.get("aud")
    resource: str | None = None
    if isinstance(audience, str):
        resource = audience
    elif isinstance(audience, list) and audience:
        first = audience[0]
        if isinstance(first, str):
            resource = first

    subject = access_token.subject
    if not subject and isinstance(claims.get("sub"), str):
        subject = claims["sub"]

    return {
        "user": {
            "id": subject or "",
            "organizationId": organization_id if isinstance(organization_id, str) else None,
            "email": email if isinstance(email, str) and email else None,
            "roles": roles,
        },
        "auth": {
            "clientId": access_token.client_id,
            "scopes": list(access_token.scopes or []),
            "expiresAt": access_token.expires_at,
            "resource": resource,
        },
    }


class PublicConfig(TypedDict, total=False):
    issuer: str
    origin_resource: str
    bundle_proxy_resource: str
    scopes_supported: list[str]
    telemetry_ingest_url: str


class PublicConfigFetchError(RuntimeError):
    """Raised when tenant public-config cannot be loaded."""

    def __init__(
        self,
        *,
        listing_slug: str,
        url: str,
        reason: str,
    ) -> None:
        self.listing_slug = listing_slug
        self.url = url
        self.reason = reason
        super().__init__(
            "Failed to load MCP Connect Auth public-config for listing "
            f"'{listing_slug}' from {url}: {reason}. "
            f"See {INTEGRATION_DOC_URL} for setup instructions."
        )


def tenant_base_url(public_config_base_url: str, listing_slug: str) -> str:
    base = public_config_base_url.rstrip("/")
    return f"{base}/connect-auth/tenants/{listing_slug}"


def public_config_url(public_config_base_url: str, listing_slug: str) -> str:
    return f"{tenant_base_url(public_config_base_url, listing_slug)}/public-config"


def jwks_url(public_config_base_url: str, listing_slug: str) -> str:
    return (
        f"{tenant_base_url(public_config_base_url, listing_slug)}/.well-known/jwks.json"
    )


def oauth_authorization_server_metadata_url(
    public_config_base_url: str,
    listing_slug: str,
) -> str:
    return (
        f"{tenant_base_url(public_config_base_url, listing_slug)}"
        "/.well-known/oauth-authorization-server"
    )


def _validate_public_config(
    payload: dict[str, object],
    *,
    listing_slug: str,
    url: str,
) -> PublicConfig:
    issuer = payload.get("issuer")
    origin_resource = payload.get("origin_resource")
    bundle_proxy_resource = payload.get("bundle_proxy_resource")
    missing: list[str] = []
    if not isinstance(issuer, str) or not issuer:
        missing.append("issuer")
    if not isinstance(origin_resource, str) or not origin_resource:
        missing.append("origin_resource")
    if not isinstance(bundle_proxy_resource, str) or not bundle_proxy_resource:
        missing.append("bundle_proxy_resource")
    if missing:
        raise PublicConfigFetchError(
            listing_slug=listing_slug,
            url=url,
            reason=f"missing required fields: {', '.join(missing)}",
        )

    assert isinstance(issuer, str)
    assert isinstance(origin_resource, str)
    assert isinstance(bundle_proxy_resource, str)

    config: PublicConfig = {
        "issuer": issuer,
        "origin_resource": origin_resource,
        "bundle_proxy_resource": bundle_proxy_resource,
    }
    scopes_supported = payload.get("scopes_supported")
    if isinstance(scopes_supported, list):
        config["scopes_supported"] = [
            scope for scope in scopes_supported if isinstance(scope, str)
        ]
    telemetry_ingest_url = payload.get("telemetry_ingest_url")
    if isinstance(telemetry_ingest_url, str) and telemetry_ingest_url:
        config["telemetry_ingest_url"] = telemetry_ingest_url
    return config


def fetch_public_config(
    listing_slug: str,
    *,
    public_config_base_url: str = DEFAULT_PUBLIC_CONFIG_BASE_URL,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
) -> PublicConfig:
    """Load tenant public-config synchronously."""
    url = public_config_url(public_config_base_url, listing_slug)
    try:
        response = httpx2.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise PublicConfigFetchError(
                listing_slug=listing_slug,
                url=url,
                reason="response was not a JSON object",
            )
        return _validate_public_config(payload, listing_slug=listing_slug, url=url)
    except httpx2.HTTPError as exc:
        raise PublicConfigFetchError(
            listing_slug=listing_slug,
            url=url,
            reason=str(exc),
        ) from exc


PublicConfigFetcher = Callable[..., PublicConfig]


class McpbundlesJWTVerifier(JWTVerifier):
    """JWT verifier with one JWKS refresh when a token references an unknown ``kid``.

    MCPBundles tenant signing keys rotate in place while cached JWKS may still
    hold the previous key. Refresh once before failing lookup.

    Connect Auth always mints ``client_id`` separately from ``sub``. This verifier
    does not fall back ``client_id`` to ``sub`` (unlike the generic ``JWTVerifier``).
    """

    async def _get_jwks_key(self, kid: str | None) -> str:
        try:
            return await super()._get_jwks_key(kid)
        except ValueError as exc:
            message = str(exc)
            if kid and "not found in JWKS" in message:
                self._jwks_cache_time = 0.0
                return await super()._get_jwks_key(kid)
            raise

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = await super().load_access_token(token)
        if access_token is None:
            return None

        claims = access_token.claims
        raw_client_id = claims.get("client_id") or claims.get("azp")
        if not isinstance(raw_client_id, str) or not raw_client_id.strip():
            self.logger.debug(
                "Bearer token rejected: Connect Auth token missing client_id claim"
            )
            return None

        if access_token.client_id != raw_client_id:
            return access_token.model_copy(update={"client_id": raw_client_id})
        return access_token


class McpbundlesConnectProvider(RemoteAuthProvider):
    """MCPBundles Connect Auth resource server provider for FastMCP.

    IMPORTANT SETUP REQUIREMENTS:

    1. Publish your MCP server on MCPBundles with MCP Connect Auth enabled.
    2. Set your federation sign-in URL and save the federation secret on your
       web app (not in this MCP server).
    3. Configure ``listing_slug`` to your published listing slug and set
       ``base_url`` to your public MCP origin URL.

    For detailed setup instructions, see:
    https://www.mcpbundles.com/docs/integrations/mcp-connect-auth

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth.providers.mcpbundles import McpbundlesConnectProvider

        auth = McpbundlesConnectProvider(
            listing_slug="my-listing",
            base_url="https://mcp.example.com",
        )
        mcp = FastMCP("My App", auth=auth)
        ```
    """

    def __init__(
        self,
        *,
        listing_slug: str,
        base_url: AnyHttpUrl | str,
        required_scopes: list[str] | None = None,
        scopes_supported: list[str] | None = None,
        resource_name: str | None = None,
        resource_documentation: AnyHttpUrl | None = None,
        token_verifier: TokenVerifier | None = None,
        public_config_base_url: str = DEFAULT_PUBLIC_CONFIG_BASE_URL,
        public_config: PublicConfig | None = None,
        public_config_fetcher: PublicConfigFetcher | None = None,
    ) -> None:
        if not listing_slug:
            raise ValueError("listing_slug is required")

        self.listing_slug = listing_slug
        self.public_config_base_url = public_config_base_url.rstrip("/")
        base_url_value = str(base_url).rstrip("/") + "/"

        fetcher = public_config_fetcher or fetch_public_config
        self.public_config = public_config or fetcher(
            listing_slug,
            public_config_base_url=self.public_config_base_url,
        )

        parsed_scopes = (
            parse_scopes(required_scopes) if required_scopes is not None else []
        )
        self.required_scopes = parsed_scopes

        issuer = self.public_config["issuer"]
        audiences = [
            self.public_config["origin_resource"],
            self.public_config["bundle_proxy_resource"],
        ]

        if token_verifier is None:
            token_verifier = McpbundlesJWTVerifier(
                jwks_uri=jwks_url(self.public_config_base_url, listing_slug),
                issuer=issuer,
                algorithm="ES256",
                audience=audiences,
                required_scopes=self.required_scopes or None,
            )

        tenant_as = AnyHttpUrl(
            tenant_base_url(self.public_config_base_url, listing_slug)
        )
        advertised_scopes = scopes_supported
        if advertised_scopes is None:
            advertised_scopes = self.public_config.get("scopes_supported")

        super().__init__(
            token_verifier=token_verifier,
            authorization_servers=[tenant_as],
            base_url=base_url_value,
            scopes_supported=advertised_scopes,
            resource_name=resource_name,
            resource_documentation=resource_documentation
            or AnyHttpUrl(INTEGRATION_DOC_URL),
        )

    def get_routes(
        self,
        mcp_path: str | None = None,
    ) -> list[Route]:
        routes = super().get_routes(mcp_path)
        metadata_url = oauth_authorization_server_metadata_url(
            self.public_config_base_url,
            self.listing_slug,
        )

        async def oauth_authorization_server_metadata(request):
            try:
                async with httpx2.AsyncClient() as client:
                    response = await client.get(metadata_url)
                    response.raise_for_status()
                    return JSONResponse(response.json())
            except Exception as exc:
                logger.error(
                    "Failed to fetch MCP Connect Auth metadata for listing %s: %s",
                    self.listing_slug,
                    exc,
                )
                return JSONResponse(
                    {
                        "error": "server_error",
                        "error_description": (
                            "Failed to fetch MCP Connect Auth authorization server "
                            f"metadata for listing '{self.listing_slug}'. "
                            f"See {INTEGRATION_DOC_URL}."
                        ),
                    },
                    status_code=500,
                )

        routes.append(
            Route(
                "/.well-known/oauth-authorization-server",
                endpoint=oauth_authorization_server_metadata,
                methods=["GET"],
            )
        )
        return routes
