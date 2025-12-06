"""
Private CIMD (Client ID Metadata Document) implementation for FastMCP.

This module implements server-side CIMD support (SEP-991) ahead of the MCP SDK.
When/if the SDK adds official server-side CIMD support, we should migrate to
using their implementation instead of this private module.

All functions and classes in this module are private (prefixed with _) to make
it easy to swap out the implementation later without breaking public API.

Reference:
- SEP-991: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/991
- IETF draft: https://datatracker.ietf.org/doc/draft-ietf-oauth-client-id-metadata-document/
"""

from __future__ import annotations

import ipaddress
import socket
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.shared.auth import OAuthClientInformationFull

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


def _is_cimd_client_id(client_id: str) -> bool:
    """Check if client_id is a URL suitable for CIMD lookup.

    Per the spec, CIMD URLs must:
    - Use HTTPS scheme
    - Have a non-root path component
    """
    if not isinstance(client_id, str):
        return False
    if not client_id.startswith("https://"):
        return False
    try:
        parsed = urlparse(client_id)
        return parsed.scheme == "https" and parsed.path not in ("", "/")
    except Exception:
        return False


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/reserved range.

    This is used for SSRF protection to prevent fetching metadata from
    internal network addresses.
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        # Check for private, loopback, link-local, etc.
        if ip.is_private:
            return True
        if ip.is_loopback:
            return True
        if ip.is_link_local:
            return True
        if ip.is_multicast:
            return True
        if ip.is_reserved:
            return True

        # For IPv4, also check for special ranges
        if isinstance(ip, ipaddress.IPv4Address):
            # 0.0.0.0/8 - "This" network
            if ip_str.startswith("0."):
                return True

        return False
    except ValueError:
        # If we can't parse the IP, treat it as suspicious
        return True


def _validate_cimd_url(url: str) -> None:
    """Validate URL for CIMD fetch, including SSRF protection.

    Raises:
        ValueError: If URL is invalid or resolves to private IP
    """
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("CIMD URL must use HTTPS")

    if parsed.path in ("", "/"):
        raise ValueError("CIMD URL must have a non-root path")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("CIMD URL must have a valid hostname")

    # DNS resolution check for SSRF protection
    try:
        # Get all IP addresses for the hostname
        _, _, ipaddrlist = socket.gethostbyname_ex(hostname)
        for ip in ipaddrlist:
            if _is_private_ip(ip):
                raise ValueError(f"CIMD URL resolves to private IP address: {ip}")
    except socket.gaierror as e:
        raise ValueError(f"Failed to resolve CIMD URL hostname: {e}") from e


async def _fetch_client_metadata(
    client_id: str,
    *,
    timeout: float = 10.0,
    max_size: int = 1_048_576,  # 1MB
) -> dict[str, Any]:
    """Fetch and parse client metadata document from URL.

    Args:
        client_id: The HTTPS URL to fetch metadata from
        timeout: Request timeout in seconds
        max_size: Maximum response size in bytes

    Returns:
        Parsed JSON metadata as a dictionary

    Raises:
        ValueError: If URL validation fails or response is too large
        httpx.HTTPError: If the HTTP request fails
    """
    _validate_cimd_url(client_id)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            client_id,
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
        response.raise_for_status()

        # Check content length header before reading body
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_size:
            raise ValueError(
                f"CIMD response too large: {content_length} bytes (max: {max_size})"
            )

        # Read response with size check
        content = response.content
        if len(content) > max_size:
            raise ValueError(
                f"CIMD response too large: {len(content)} bytes (max: {max_size})"
            )

        return response.json()


def _create_client_from_metadata(
    client_id: str,
    metadata: dict[str, Any],
) -> OAuthClientInformationFull:
    """Convert fetched metadata to OAuthClientInformationFull.

    Args:
        client_id: The URL used to fetch the metadata (must match client_id in doc)
        metadata: The parsed metadata document

    Returns:
        OAuthClientInformationFull instance

    Raises:
        ValueError: If client_id in metadata doesn't match URL
    """
    # Validate that client_id in the document matches the URL
    doc_client_id = metadata.get("client_id")
    if doc_client_id != client_id:
        raise ValueError(
            f"client_id in metadata ({doc_client_id}) doesn't match URL ({client_id})"
        )

    # Ensure token_endpoint_auth_method defaults to "none" for CIMD clients
    # (they don't have client secrets)
    if "token_endpoint_auth_method" not in metadata:
        metadata = {**metadata, "token_endpoint_auth_method": "none"}

    return OAuthClientInformationFull.model_validate(metadata)


class _CIMDCache:
    """Simple in-memory cache for CIMD metadata with TTL support.

    Per the spec, servers SHOULD cache metadata respecting HTTP headers,
    with a maximum of 24 hours.
    """

    def __init__(
        self,
        default_ttl: int = 3600,  # 1 hour default
        max_ttl: int = 86400,  # 24 hours max per spec
    ):
        self._cache: dict[str, tuple[OAuthClientInformationFull, float]] = {}
        self._default_ttl = default_ttl
        self._max_ttl = max_ttl

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        """Get cached client info if present and not expired."""
        if client_id not in self._cache:
            return None

        client_info, expires_at = self._cache[client_id]
        if time.time() > expires_at:
            del self._cache[client_id]
            return None

        return client_info

    def set(
        self,
        client_id: str,
        client_info: OAuthClientInformationFull,
        ttl: int | None = None,
    ) -> None:
        """Cache client info with TTL (capped at max_ttl)."""
        effective_ttl = min(ttl or self._default_ttl, self._max_ttl)
        expires_at = time.time() + effective_ttl
        self._cache[client_id] = (client_info, expires_at)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()


async def _get_cimd_client(
    client_id: str,
    cache: _CIMDCache | None = None,
) -> OAuthClientInformationFull:
    """Main entry point - fetch and validate CIMD client.

    Args:
        client_id: The HTTPS URL to use as client_id
        cache: Optional cache instance for storing results

    Returns:
        OAuthClientInformationFull for the client

    Raises:
        ValueError: If validation fails
        httpx.HTTPError: If fetch fails
    """
    # Check cache first
    if cache:
        cached = cache.get(client_id)
        if cached is not None:
            logger.debug(f"CIMD cache hit for {client_id}")
            return cached

    logger.debug(f"Fetching CIMD metadata from {client_id}")

    # Fetch and validate
    metadata = await _fetch_client_metadata(client_id)
    client_info = _create_client_from_metadata(client_id, metadata)

    # Cache result
    if cache:
        cache.set(client_id, client_info)

    return client_info
