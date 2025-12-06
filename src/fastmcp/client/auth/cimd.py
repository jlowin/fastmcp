"""
Utility for creating CIMD (Client ID Metadata Documents).

CIMD allows OAuth clients to be identified by a URL pointing to their
metadata document, eliminating the need for Dynamic Client Registration (DCR).

See SEP-991: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/991
"""

from __future__ import annotations

from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

__all__ = ["create_cimd_document"]

# Common localhost redirect URIs for OAuth callbacks
DEFAULT_REDIRECT_URIS = [
    "http://localhost:8080/callback",
    "http://localhost:8888/callback",
    "http://localhost:9000/callback",
    "http://127.0.0.1:8080/callback",
    "http://127.0.0.1:8888/callback",
    "http://127.0.0.1:9000/callback",
]


def create_cimd_document(
    url: str,
    *,
    client_name: str = "FastMCP Client",
    redirect_uris: list[str] | None = None,
    scopes: list[str] | None = None,
) -> dict:
    """
    Create a CIMD (Client ID Metadata Document) for hosting.

    The returned dict should be serialized as JSON and served at the given URL.
    The URL itself becomes the OAuth client_id.

    Args:
        url: The HTTPS URL where this document will be hosted.
             Must use HTTPS and have a non-root path.
             This exact URL becomes the client_id.
        client_name: Human-readable name for the client.
        redirect_uris: OAuth callback URIs. Defaults to common localhost variants
            for development use.
        scopes: OAuth scopes to request (e.g., ["openid", "profile", "email"]).

    Returns:
        Dict ready to serialize as JSON and host at the URL.

    Raises:
        ValueError: If URL doesn't use HTTPS or has no path.

    Example:
        >>> import json
        >>> doc = create_cimd_document(
        ...     "https://example.com/.well-known/oauth-client.json",
        ...     client_name="My App",
        ...     scopes=["openid", "profile"],
        ... )
        >>> print(json.dumps(doc, indent=2))
        {
          "client_id": "https://example.com/.well-known/oauth-client.json",
          "client_name": "My App",
          "redirect_uris": ["http://localhost:8080/callback", ...],
          "grant_types": ["authorization_code", "refresh_token"],
          "response_types": ["code"],
          "token_endpoint_auth_method": "none",
          "scope": "openid profile"
        }
    """
    if not url.startswith("https://"):
        raise ValueError("CIMD URL must use HTTPS")

    # Check for non-root path
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.path in ("", "/"):
        raise ValueError("CIMD URL must have a non-root path")

    client = OAuthClientInformationFull(
        client_id=url,
        client_name=client_name,
        redirect_uris=[AnyUrl(u) for u in (redirect_uris or DEFAULT_REDIRECT_URIS)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        scope=" ".join(scopes) if scopes else None,
    )

    return client.model_dump(mode="json", exclude_none=True)
