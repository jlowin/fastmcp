"""CIMD (Client ID Metadata Document) support for FastMCP.

CIMD is a simpler alternative to Dynamic Client Registration where clients
host a static JSON document at an HTTPS URL, and that URL becomes their
client_id. See the IETF draft: draft-parecki-oauth-client-id-metadata-document

This module provides:
- CIMDDocument: Pydantic model for CIMD document validation
- CIMDFetcher: Fetch and validate CIMD documents with SSRF protection
- CIMDClientManager: Manages CIMD client operations
"""

from __future__ import annotations

import fnmatch
import ipaddress
import json
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


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


class CIMDValidationError(Exception):
    """Raised when CIMD document validation fails."""


class CIMDFetchError(Exception):
    """Raised when CIMD document fetching fails."""


class CIMDFetcher:
    """Fetch and validate CIMD documents with security.

    Handles:
    - URL validation (HTTPS, non-root path)
    - SSRF protection (block private/loopback addresses)
    - Document fetching with timeout
    - Validation that client_id matches URL

    Note: CIMD clients are stored in persistent storage after first fetch,
    so no in-memory caching is needed.
    """

    def __init__(
        self,
        cache_ttl: int = 3600,  # Kept for backwards compatibility, unused
        min_cache_ttl: int = 300,  # Kept for backwards compatibility, unused
        max_cache_ttl: int = 86400,  # Kept for backwards compatibility, unused
        timeout: float = 10.0,
    ):
        """Initialize the CIMD fetcher.

        Args:
            cache_ttl: Deprecated, unused (kept for compatibility)
            min_cache_ttl: Deprecated, unused (kept for compatibility)
            max_cache_ttl: Deprecated, unused (kept for compatibility)
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout

    def is_cimd_client_id(self, client_id: str) -> bool:
        """Check if a client_id looks like a CIMD URL.

        CIMD URLs must be HTTPS with a host and non-root path.
        """
        if not client_id:
            return False
        try:
            parsed = urlparse(client_id)
            return (
                parsed.scheme == "https"
                and bool(parsed.netloc)  # Must have a host
                and parsed.path not in ("", "/")
            )
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
                "169.254.",  # Link-local
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

    async def fetch(self, client_id_url: str) -> CIMDDocument:
        """Fetch and validate a CIMD document with SSRF protection.

        This method implements SSRF protection by:
        1. Requiring HTTPS only
        2. Blocking private/loopback IP addresses and hostnames
        3. Limiting response size to 5KB (prevents DoS via streaming)
        4. Disabling redirects (prevents redirect-based SSRF)
        5. Using aggressive timeouts

        Args:
            client_id_url: The URL to fetch (also the expected client_id)

        Returns:
            Validated CIMDDocument

        Raises:
            CIMDValidationError: If document is invalid
            CIMDFetchError: If document cannot be fetched
        """
        # Parse and validate URL format
        try:
            parsed = urlparse(client_id_url)
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
        port = parsed.port

        # Validate hostname is not private/loopback
        if self._is_private_ip(hostname):
            raise CIMDValidationError(
                f"CIMD URLs cannot use private/loopback addresses: {hostname}"
            )

        # Validate port - only allow standard HTTPS (443) or explicit non-standard
        # Non-standard ports are allowed but logged for visibility
        if port is not None and port != 443:
            logger.warning(
                "CIMD URL uses non-standard port %d: %s", port, client_id_url
            )

        # Fetch document with streaming to prevent memory exhaustion
        max_size = 5120  # 5KB max for CIMD documents
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=False,  # Disable redirects to prevent SSRF bypass
                ) as client,
                client.stream("GET", client_id_url) as response,
            ):
                if response.status_code != 200:
                    raise CIMDFetchError(
                        f"CIMD document returned status {response.status_code}: {client_id_url}"
                    )

                # Check Content-Length header first if available
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > max_size:
                            raise CIMDFetchError(
                                f"Response too large: {size} bytes (max 5KB for CIMD documents)"
                            )
                    except ValueError:
                        pass  # Invalid header, will check during streaming

                # Stream response and enforce size limit
                chunks = []
                total_size = 0
                async for chunk in response.aiter_bytes():
                    total_size += len(chunk)
                    if total_size > max_size:
                        raise CIMDFetchError(
                            f"Response too large: exceeded {max_size} bytes (max 5KB for CIMD documents)"
                        )
                    chunks.append(chunk)

                content = b"".join(chunks)

        except httpx.TimeoutException as e:
            raise CIMDFetchError(
                f"Timeout fetching CIMD document: {client_id_url}"
            ) from e
        except httpx.RequestError as e:
            raise CIMDFetchError(f"Error fetching CIMD document: {e}") from e

        # Parse document
        try:
            data = json.loads(content)
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
                if fnmatch.fnmatch(redirect_uri, allowed_str):
                    return True

        return False


class CIMDAssertionValidator:
    """Validates JWT assertions for private_key_jwt CIMD clients.

    Implements RFC 7523 (JSON Web Token (JWT) Profile for OAuth 2.0 Client
    Authentication and Authorization Grants) for CIMD client authentication.
    """

    def __init__(self):
        self._jti_cache: set[str] = set()
        self._jti_cache_max_size = 10000
        self.logger = get_logger(__name__)

    async def validate_assertion(
        self,
        assertion: str,
        client_id: str,
        token_endpoint: str,
        cimd_doc: CIMDDocument,
    ) -> bool:
        """Validate JWT assertion from client.

        Args:
            assertion: The JWT assertion string
            client_id: Expected client_id (must match iss and sub claims)
            token_endpoint: Token endpoint URL (must match aud claim)
            cimd_doc: CIMD document containing JWKS for key verification

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        # 1. Validate CIMD document has key material
        if cimd_doc.jwks_uri:
            # Use JWTVerifier to handle JWKS fetching, caching, and JWT validation
            verifier = JWTVerifier(
                jwks_uri=str(cimd_doc.jwks_uri),
                issuer=client_id,  # Must match client_id per RFC 7523
                audience=token_endpoint,  # Must match token endpoint
            )
        elif cimd_doc.jwks:
            # Extract public key from inline JWKS
            public_key = self._extract_public_key_from_jwks(assertion, cimd_doc.jwks)
            verifier = JWTVerifier(
                public_key=public_key,
                issuer=client_id,
                audience=token_endpoint,
            )
        else:
            raise ValueError(
                "CIMD document must have jwks_uri or jwks for private_key_jwt"
            )

        # 2. Verify JWT using JWTVerifier (handles signature, exp, iss, aud)
        access_token = await verifier.load_access_token(assertion)
        if not access_token:
            raise ValueError("Invalid JWT assertion")

        claims = access_token.claims

        # 3. Additional RFC 7523 validation: sub claim must equal client_id
        if claims.get("sub") != client_id:
            raise ValueError(f"Assertion sub claim must be {client_id}")

        # 4. Check jti for replay attacks (RFC 7523 requirement)
        jti = claims.get("jti")
        if not jti:
            raise ValueError("Assertion must include jti claim")
        if jti in self._jti_cache:
            raise ValueError(f"Assertion replay detected: jti {jti} already used")

        # Add to cache (with size limit)
        self._jti_cache.add(jti)
        if len(self._jti_cache) > self._jti_cache_max_size:
            # Evict arbitrary element to maintain bounded memory
            self._jti_cache.pop()

        self.logger.debug(
            "JWT assertion validated successfully for client %s", client_id
        )
        return True

    def _extract_public_key_from_jwks(self, token: str, jwks: dict) -> str:
        """Extract public key from inline JWKS.

        Args:
            token: JWT token to extract kid from
            jwks: JWKS document containing keys

        Returns:
            PEM-encoded public key

        Raises:
            ValueError: If key cannot be found or extracted
        """
        import base64
        import json

        from authlib.jose import JsonWebKey

        # Extract kid from token header
        try:
            header_b64 = token.split(".")[0]
            header_b64 += "=" * (4 - len(header_b64) % 4)  # Add padding
            header = json.loads(base64.urlsafe_b64decode(header_b64))
            kid = header.get("kid")
        except Exception as e:
            raise ValueError(f"Failed to extract key ID from token: {e}") from e

        # Find matching key in JWKS
        keys = jwks.get("keys", [])
        if not keys:
            raise ValueError("JWKS document contains no keys")

        matching_key = None
        for key in keys:
            if kid and key.get("kid") == kid:
                matching_key = key
                break

        if not matching_key:
            # If no kid match, try first key as fallback
            if len(keys) == 1:
                matching_key = keys[0]
                self.logger.warning(
                    "No matching kid in JWKS, using single available key"
                )
            else:
                raise ValueError(f"No matching key found for kid={kid} in JWKS")

        # Convert JWK to PEM
        try:
            jwk = JsonWebKey.import_key(matching_key)
            return jwk.as_pem().decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to convert JWK to PEM: {e}") from e


class CIMDClientManager:
    """Manages all CIMD client operations for OAuth proxy.

    This class encapsulates:
    - CIMD client detection
    - Document fetching and validation
    - Synthetic OAuth client creation
    - Trust policy enforcement
    - Private key JWT assertion validation

    This allows the OAuth proxy to delegate all CIMD-specific logic to a
    single, focused manager class.
    """

    def __init__(
        self,
        enable_cimd: bool = True,
        default_scope: str = "",
        allowed_redirect_uri_patterns: list[str] | None = None,
    ):
        """Initialize CIMD client manager.

        Args:
            enable_cimd: Whether CIMD support is enabled
            default_scope: Default scope for CIMD clients if not specified in document
            allowed_redirect_uri_patterns: Allowed redirect URI patterns (proxy's config)
        """
        self.enabled = enable_cimd
        self.default_scope = default_scope
        self.allowed_redirect_uri_patterns = allowed_redirect_uri_patterns

        self._fetcher = CIMDFetcher()
        self._assertion_validator = CIMDAssertionValidator()
        self.logger = get_logger(__name__)

    def is_cimd_client_id(self, client_id: str) -> bool:
        """Check if client_id is a CIMD URL.

        Args:
            client_id: Client ID to check

        Returns:
            True if client_id is an HTTPS URL (CIMD format)
        """
        return self.enabled and self._fetcher.is_cimd_client_id(client_id)

    async def get_client(self, client_id_url: str):
        """Fetch CIMD document and create synthetic OAuth client.

        Args:
            client_id_url: HTTPS URL pointing to CIMD document

        Returns:
            OAuthProxyClient with CIMD document attached, or None if fetch fails

        Note:
            Return type is left untyped to avoid circular import with oauth_proxy.
            Returns OAuthProxyClient instance or None.
        """
        if not self.enabled:
            return None

        try:
            cimd_doc = await self._fetcher.fetch(client_id_url)
        except (CIMDFetchError, CIMDValidationError) as e:
            self.logger.warning("CIMD fetch failed for %s: %s", client_id_url, e)
            return None

        # Import here to avoid circular dependency
        from fastmcp.server.auth.oauth_proxy import OAuthProxyClient

        # Create synthetic client from CIMD document
        # Use proxy's allowed_redirect_uri_patterns, NOT the CIMD document's redirect_uris
        client = OAuthProxyClient(
            client_id=client_id_url,
            client_secret=None,
            redirect_uris=None,
            grant_types=cimd_doc.grant_types,
            scope=cimd_doc.scope or self.default_scope,
            token_endpoint_auth_method=cimd_doc.token_endpoint_auth_method,
            allowed_redirect_uri_patterns=self.allowed_redirect_uri_patterns,
            client_name=cimd_doc.client_name,
            cimd_document=cimd_doc,
        )

        self.logger.debug(
            "CIMD client resolved: %s (name=%s)",
            client_id_url,
            cimd_doc.client_name,
        )
        return client

    async def validate_private_key_jwt(
        self,
        assertion: str,
        client,  # OAuthProxyClient, untyped to avoid circular import
        token_endpoint: str,
    ) -> bool:
        """Validate JWT assertion for private_key_jwt auth.

        Args:
            assertion: JWT assertion string from client
            client: OAuth proxy client (must have cimd_document)
            token_endpoint: Token endpoint URL for aud validation

        Returns:
            True if assertion is valid

        Raises:
            ValueError: If client doesn't have CIMD document or validation fails
        """
        if not hasattr(client, "cimd_document") or not client.cimd_document:
            raise ValueError("Client must have CIMD document for private_key_jwt")

        cimd_doc = client.cimd_document
        if cimd_doc.token_endpoint_auth_method != "private_key_jwt":
            raise ValueError("CIMD document must specify private_key_jwt auth method")

        return await self._assertion_validator.validate_assertion(
            assertion, client.client_id, token_endpoint, cimd_doc
        )
