"""
Utility for creating CIMD (Client ID Metadata Documents).

CIMD allows OAuth clients to be identified by a URL pointing to their
metadata document, eliminating the need for Dynamic Client Registration (DCR).

See:
- SEP-991: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/991
- IETF Draft: https://www.ietf.org/archive/id/draft-ietf-oauth-client-id-metadata-document-00.html
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import AnyHttpUrl

__all__ = ["create_cimd_document"]


def _validate_cimd_url(url: str) -> None:
    """Validate URL meets CIMD requirements per IETF draft."""
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("CIMD URL must use HTTPS")

    if parsed.path in ("", "/"):
        raise ValueError("CIMD URL must have a non-root path")

    if parsed.fragment:
        raise ValueError("CIMD URL must not contain a fragment")

    if parsed.username or parsed.password:
        raise ValueError("CIMD URL must not contain credentials")

    # Check for dot segments (. or ..) in path
    path_segments = parsed.path.split("/")
    if any(seg in (".", "..") for seg in path_segments):
        raise ValueError("CIMD URL path must not contain dot segments")


def create_cimd_document(
    url: str,
    *,
    redirect_uris: list[str],
    client_name: str = "FastMCP Client",
    scopes: list[str] | None = None,
    jwks_uri: str | None = None,
    jwks: dict[str, Any] | None = None,
    client_uri: str | None = None,
    logo_uri: str | None = None,
    contacts: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a CIMD (Client ID Metadata Document) for hosting.

    The returned dict should be serialized as JSON and served at the given URL.
    The URL itself becomes the OAuth client_id.

    For **public clients** (CLI apps, mobile apps), omit jwks_uri/jwks.
    These clients use PKCE for security but cannot prove client identity.

    For **confidential clients**, provide jwks_uri or jwks containing your
    public key(s). The client must sign JWTs with the corresponding private
    key when calling the token endpoint, proving ownership of the client_id.

    Args:
        url: The HTTPS URL where this document will be hosted.
             Must use HTTPS, have a non-root path, no fragment, no credentials.
             This exact URL becomes the client_id.
        redirect_uris: OAuth callback URIs. These must exactly match where your
             OAuth client will receive callbacks.
        client_name: Human-readable name for the client (displayed during consent).
        scopes: OAuth scopes to request (e.g., ["openid", "profile", "email"]).
        jwks_uri: URL to JSON Web Key Set for confidential clients.
             When provided, token_endpoint_auth_method is set to "private_key_jwt".
        jwks: Inline JSON Web Key Set (alternative to jwks_uri).
             When provided, token_endpoint_auth_method is set to "private_key_jwt".
        client_uri: URL to client's homepage (displayed during consent).
        logo_uri: URL to client's logo image (displayed during consent).
        contacts: List of contact emails for the client developer.

    Returns:
        Dict ready to serialize as JSON and host at the URL.

    Raises:
        ValueError: If URL is invalid or both jwks_uri and jwks are provided.

    Example (public client):
        >>> doc = create_cimd_document(
        ...     "https://example.com/.well-known/oauth-client.json",
        ...     redirect_uris=["http://localhost:8080/callback"],
        ...     client_name="My CLI App",
        ... )
        >>> doc["token_endpoint_auth_method"]
        'none'

    Example (confidential client):
        >>> doc = create_cimd_document(
        ...     "https://example.com/.well-known/oauth-client.json",
        ...     redirect_uris=["https://example.com/callback"],
        ...     client_name="My Web App",
        ...     jwks_uri="https://example.com/.well-known/jwks.json",
        ... )
        >>> doc["token_endpoint_auth_method"]
        'private_key_jwt'
    """
    _validate_cimd_url(url)

    if jwks_uri and jwks:
        raise ValueError("Provide either jwks_uri or jwks, not both")

    # Determine auth method based on whether keys are provided
    is_confidential = jwks_uri is not None or jwks is not None
    token_endpoint_auth_method = "private_key_jwt" if is_confidential else "none"

    # Build the document
    # Using dict directly instead of OAuthClientInformationFull to include jwks fields
    doc: dict[str, Any] = {
        "client_id": url,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": token_endpoint_auth_method,
    }

    # Add optional fields
    if scopes:
        doc["scope"] = " ".join(scopes)

    if jwks_uri:
        doc["jwks_uri"] = jwks_uri

    if jwks:
        doc["jwks"] = jwks

    if client_uri:
        # Validate it's a valid URL
        AnyHttpUrl(client_uri)
        doc["client_uri"] = client_uri

    if logo_uri:
        # Validate it's a valid URL
        AnyHttpUrl(logo_uri)
        doc["logo_uri"] = logo_uri

    if contacts:
        doc["contacts"] = contacts

    return doc
