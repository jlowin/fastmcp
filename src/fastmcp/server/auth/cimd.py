"""CIMD (Client ID Metadata Document) support for FastMCP.

CIMD is a simpler alternative to Dynamic Client Registration where clients
host a static JSON document at an HTTPS URL, and that URL becomes their
client_id. See the IETF draft: draft-parecki-oauth-client-id-metadata-document

This module provides:
- CIMDDocument: Pydantic model for CIMD document validation
- CIMDFetcher: Fetch and validate CIMD documents with caching/security
- CIMDTrustPolicy: Configurable trust levels for CIMD clients
"""

from __future__ import annotations

import ipaddress
import time
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


# Default trusted domains that can skip consent
DEFAULT_TRUSTED_CIMD_DOMAINS: list[str] = [
    "claude.ai",
    "anthropic.com",
    "cursor.com",
]


class CIMDDocument(BaseModel):
    """CIMD document per draft-parecki-oauth-client-id-metadata-document.

    The client metadata document is a JSON document containing OAuth client
    metadata. The client_id property MUST match the URL where this document
    is hosted.

    Key constraint: token_endpoint_auth_method MUST NOT use shared secrets
    (client_secret_post, client_secret_basic, client_secret_jwt).
    """

    client_id: AnyHttpUrl = Field(
        ...,
        description="Must match the URL where this document is hosted",
    )
    client_name: str | None = Field(
        default=None,
        description="Human-readable name of the client",
    )
    client_uri: AnyHttpUrl | None = Field(
        default=None,
        description="URL of the client's home page",
    )
    logo_uri: AnyHttpUrl | None = Field(
        default=None,
        description="URL of the client's logo image",
    )
    redirect_uris: list[str] | None = Field(
        default=None,
        description="Array of allowed redirect URIs (may include wildcards like http://localhost:*/callback)",
    )
    token_endpoint_auth_method: Literal["none", "private_key_jwt"] = Field(
        default="none",
        description="Authentication method for token endpoint (no shared secrets allowed)",
    )
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code"],
        description="OAuth grant types the client will use",
    )
    response_types: list[str] = Field(
        default_factory=lambda: ["code"],
        description="OAuth response types the client will use",
    )
    scope: str | None = Field(
        default=None,
        description="Space-separated list of scopes the client may request",
    )
    contacts: list[str] | None = Field(
        default=None,
        description="Contact information for the client developer",
    )
    tos_uri: AnyHttpUrl | None = Field(
        default=None,
        description="URL of the client's terms of service",
    )
    policy_uri: AnyHttpUrl | None = Field(
        default=None,
        description="URL of the client's privacy policy",
    )
    jwks_uri: AnyHttpUrl | None = Field(
        default=None,
        description="URL of the client's JSON Web Key Set (for private_key_jwt)",
    )
    jwks: dict[str, Any] | None = Field(
        default=None,
        description="Client's JSON Web Key Set (for private_key_jwt)",
    )
    software_id: str | None = Field(
        default=None,
        description="Unique identifier for the client software",
    )
    software_version: str | None = Field(
        default=None,
        description="Version of the client software",
    )

    @field_validator("token_endpoint_auth_method")
    @classmethod
    def validate_auth_method(cls, v: str) -> str:
        """Ensure no shared-secret auth methods are used."""
        forbidden = {"client_secret_post", "client_secret_basic", "client_secret_jwt"}
        if v in forbidden:
            raise ValueError(
                f"CIMD documents cannot use shared-secret auth methods: {v}. "
                "Use 'none' or 'private_key_jwt' instead."
            )
        return v


class CIMDTrustPolicy(BaseModel):
    """Trust policy for CIMD clients.

    Controls how CIMD clients are treated during authorization:
    - Trusted domains can skip consent entirely
    - Unknown domains show consent with verified badge
    - Blocked domains are rejected
    """

    trusted_domains: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TRUSTED_CIMD_DOMAINS),
        description="Domains that can skip consent (e.g., claude.ai)",
    )
    blocked_domains: list[str] = Field(
        default_factory=list,
        description="Domains that are always rejected",
    )
    auto_approve_trusted: bool = Field(
        default=True,
        description="Whether trusted domains skip consent entirely",
    )
    require_consent_for_unknown: bool = Field(
        default=True,
        description="Whether unknown CIMD clients require consent",
    )

    def is_trusted(self, domain: str) -> bool:
        """Check if a domain is in the trusted list."""
        domain = domain.lower()
        return any(
            domain == trusted.lower() or domain.endswith("." + trusted.lower())
            for trusted in self.trusted_domains
        )

    def is_blocked(self, domain: str) -> bool:
        """Check if a domain is in the blocked list."""
        domain = domain.lower()
        return any(
            domain == blocked.lower() or domain.endswith("." + blocked.lower())
            for blocked in self.blocked_domains
        )


class CIMDValidationError(Exception):
    """Raised when CIMD document validation fails."""


class CIMDFetchError(Exception):
    """Raised when CIMD document fetching fails."""


class CIMDFetcher:
    """Fetch and validate CIMD documents with caching and security.

    Handles:
    - URL validation (HTTPS, non-root path)
    - SSRF protection (block private/loopback addresses)
    - Document fetching with timeout
    - Validation that client_id matches URL
    - Caching with configurable TTL
    """

    def __init__(
        self,
        cache_ttl: int = 3600,
        min_cache_ttl: int = 300,
        max_cache_ttl: int = 86400,
        timeout: float = 10.0,
        trust_policy: CIMDTrustPolicy | None = None,
    ):
        """Initialize the CIMD fetcher.

        Args:
            cache_ttl: Default cache TTL in seconds (default 1 hour)
            min_cache_ttl: Minimum cache TTL to prevent hammering (default 5 min)
            max_cache_ttl: Maximum cache TTL per spec (default 24 hours)
            timeout: HTTP request timeout in seconds
            trust_policy: Trust policy for domain handling
        """
        self.cache_ttl = cache_ttl
        self.min_cache_ttl = min_cache_ttl
        self.max_cache_ttl = max_cache_ttl
        self.timeout = timeout
        self.trust_policy = trust_policy or CIMDTrustPolicy()
        self._cache: dict[str, tuple[CIMDDocument, float]] = {}

    def is_cimd_client_id(self, client_id: str) -> bool:
        """Check if a client_id looks like a CIMD URL.

        CIMD URLs must be HTTPS with a non-root path.
        """
        if not client_id:
            return False
        try:
            parsed = urlparse(client_id)
            return parsed.scheme == "https" and parsed.path not in ("", "/")
        except Exception:
            return False

    def _is_private_ip(self, hostname: str) -> bool:
        """Check if hostname resolves to a private/loopback IP (SSRF protection)."""
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_reserved
        except ValueError:
            # Not an IP address, could be a hostname
            # For hostnames, we check common private patterns
            hostname_lower = hostname.lower()
            private_patterns = [
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
                "::1",
                "10.",
                "172.16.",
                "172.17.",
                "172.18.",
                "172.19.",
                "172.20.",
                "172.21.",
                "172.22.",
                "172.23.",
                "172.24.",
                "172.25.",
                "172.26.",
                "172.27.",
                "172.28.",
                "172.29.",
                "172.30.",
                "172.31.",
                "192.168.",
                ".local",
                ".internal",
            ]
            return any(
                hostname_lower == p
                or hostname_lower.startswith(p)
                or hostname_lower.endswith(p)
                for p in private_patterns
            )

    def _validate_url(self, url: str) -> tuple[str, str]:
        """Validate CIMD URL and return (hostname, path).

        Raises:
            CIMDValidationError: If URL is invalid
        """
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise CIMDValidationError(f"Invalid URL: {e}") from e

        if parsed.scheme != "https":
            raise CIMDValidationError(f"CIMD URLs must use HTTPS, got: {parsed.scheme}")

        if not parsed.netloc:
            raise CIMDValidationError("CIMD URLs must have a host")

        if parsed.path in ("", "/"):
            raise CIMDValidationError(
                "CIMD URLs must have a non-root path (e.g., /client.json)"
            )

        hostname = parsed.hostname or parsed.netloc
        if self._is_private_ip(hostname):
            raise CIMDValidationError(
                f"CIMD URLs cannot point to private/loopback addresses: {hostname}"
            )

        if self.trust_policy.is_blocked(hostname):
            raise CIMDValidationError(f"Domain is blocked: {hostname}")

        return hostname, parsed.path

    def _get_cached(self, url: str) -> CIMDDocument | None:
        """Get cached document if still valid."""
        if url in self._cache:
            doc, expires_at = self._cache[url]
            if time.time() < expires_at:
                logger.debug("CIMD cache hit: %s", url)
                return doc
            else:
                del self._cache[url]
        return None

    def _cache_document(
        self, url: str, doc: CIMDDocument, cache_control: str | None = None
    ) -> None:
        """Cache document with appropriate TTL."""
        ttl = self.cache_ttl

        # Parse Cache-Control header if present
        if cache_control:
            for directive in cache_control.split(","):
                directive = directive.strip().lower()
                if directive.startswith("max-age="):
                    parts = directive.split("=")
                    if len(parts) >= 2 and parts[1].isdigit():
                        ttl = int(parts[1])
                elif directive in ("no-store", "no-cache"):
                    ttl = self.min_cache_ttl  # Still cache briefly to prevent abuse

        # Clamp TTL to bounds
        ttl = max(self.min_cache_ttl, min(ttl, self.max_cache_ttl))

        expires_at = time.time() + ttl
        self._cache[url] = (doc, expires_at)
        logger.debug("CIMD cached: %s (TTL=%ds)", url, ttl)

    async def fetch(self, client_id_url: str) -> CIMDDocument:
        """Fetch and validate a CIMD document.

        Args:
            client_id_url: The URL to fetch (also the expected client_id)

        Returns:
            Validated CIMDDocument

        Raises:
            CIMDValidationError: If document is invalid
            CIMDFetchError: If document cannot be fetched
        """
        # Check cache first
        cached = self._get_cached(client_id_url)
        if cached:
            return cached

        # Validate URL (also checks SSRF, blocked domains)
        self._validate_url(client_id_url)

        # Fetch document
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    client_id_url,
                    headers={"Accept": "application/json"},
                    follow_redirects=True,
                )
        except httpx.TimeoutException as e:
            raise CIMDFetchError(
                f"Timeout fetching CIMD document: {client_id_url}"
            ) from e
        except httpx.RequestError as e:
            raise CIMDFetchError(f"Error fetching CIMD document: {e}") from e

        if response.status_code != 200:
            raise CIMDFetchError(
                f"CIMD document returned status {response.status_code}: {client_id_url}"
            )

        # Parse document
        try:
            data = response.json()
        except Exception as e:
            raise CIMDValidationError(f"CIMD document is not valid JSON: {e}") from e

        # Validate as CIMDDocument
        try:
            doc = CIMDDocument.model_validate(data)
        except Exception as e:
            raise CIMDValidationError(f"Invalid CIMD document: {e}") from e

        # Critical: client_id must match the URL
        if str(doc.client_id).rstrip("/") != client_id_url.rstrip("/"):
            raise CIMDValidationError(
                f"CIMD client_id mismatch: document says '{doc.client_id}' "
                f"but was fetched from '{client_id_url}'"
            )

        # Cache the document
        cache_control = response.headers.get("cache-control")
        self._cache_document(client_id_url, doc, cache_control)

        logger.info(
            "CIMD document fetched: %s (client_name=%s)",
            client_id_url,
            doc.client_name,
        )

        return doc

    def validate_redirect_uri(self, doc: CIMDDocument, redirect_uri: str) -> bool:
        """Validate that a redirect_uri is allowed by the CIMD document.

        Args:
            doc: The CIMD document
            redirect_uri: The redirect URI to validate

        Returns:
            True if valid, False otherwise
        """
        if not doc.redirect_uris:
            # No redirect_uris specified - reject all
            return False

        # Normalize for comparison
        redirect_uri = redirect_uri.rstrip("/")

        for allowed in doc.redirect_uris:
            allowed_str = allowed.rstrip("/")
            if redirect_uri == allowed_str:
                return True

            # Check for wildcard port matching (http://localhost:*/callback)
            if "*" in allowed_str:
                # Simple wildcard matching for port
                import fnmatch

                if fnmatch.fnmatch(redirect_uri, allowed_str):
                    return True

        return False

    def get_domain(self, client_id_url: str) -> str | None:
        """Extract domain from a CIMD URL."""
        try:
            parsed = urlparse(client_id_url)
            return parsed.hostname
        except Exception:
            return None

    def clear_cache(self, url: str | None = None) -> None:
        """Clear cached documents.

        Args:
            url: Specific URL to clear, or None to clear all
        """
        if url:
            self._cache.pop(url, None)
        else:
            self._cache.clear()
