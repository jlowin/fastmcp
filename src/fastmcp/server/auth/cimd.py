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

import asyncio
import fnmatch
import ipaddress
import json
import socket
import time
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from fastmcp.server.auth.ssrf import format_ip_for_url
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


def _is_ip_allowed(ip_str: str) -> bool:
    """Check if an IP address is allowed (must be globally routable unicast).

    This is the core SSRF protection - it validates actual resolved IP addresses,
    not hostnames. This prevents DNS rebinding and IP obfuscation attacks.

    Uses ip.is_global which catches:
    - Private (10.x, 172.16-31.x, 192.168.x)
    - Loopback (127.x, ::1)
    - Link-local (169.254.x, fe80::) - includes AWS metadata!
    - Reserved, unspecified
    - RFC6598 Carrier-Grade NAT (100.64.0.0/10) - can point to internal networks

    Additionally blocks multicast addresses (not caught by is_global).

    Args:
        ip_str: IP address string to check

    Returns:
        True if the IP is allowed (public unicast internet), False if blocked
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # If we can't parse it as an IP, block it
        return False

    # Must be globally routable
    if not ip.is_global:
        return False

    # Block multicast (not caught by is_global for some ranges)
    if ip.is_multicast:
        return False

    # IPv6-specific checks for embedded IPv4 addresses
    if isinstance(ip, ipaddress.IPv6Address):
        # Block IPv4-mapped IPv6 addresses (::ffff:127.0.0.1)
        if ip.ipv4_mapped:
            return _is_ip_allowed(str(ip.ipv4_mapped))
        # Block 6to4 addresses (2002::/16) - can encode IPv4
        if ip.sixtofour:
            return _is_ip_allowed(str(ip.sixtofour))
        # Block Teredo addresses (2001::/32) - can tunnel to IPv4
        if ip.teredo:
            # teredo returns (server, client) tuple
            server, client = ip.teredo
            return _is_ip_allowed(str(server)) and _is_ip_allowed(str(client))

    return True


async def _resolve_hostname(hostname: str, port: int = 443) -> list[str]:
    """Resolve hostname to IP addresses using DNS.

    This runs DNS resolution in a thread pool to avoid blocking.

    Args:
        hostname: Hostname to resolve
        port: Port number (used for getaddrinfo)

    Returns:
        List of resolved IP addresses

    Raises:
        CIMDValidationError: If resolution fails
    """
    loop = asyncio.get_event_loop()
    try:
        # Run DNS resolution in thread pool
        infos = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(
                hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM
            ),
        )
        # Extract unique IP addresses
        ips = list({info[4][0] for info in infos})
        if not ips:
            raise CIMDValidationError(
                f"DNS resolution returned no addresses for {hostname}"
            )
        return ips
    except socket.gaierror as e:
        raise CIMDValidationError(f"DNS resolution failed for {hostname}: {e}") from e


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
    """Fetch and validate CIMD documents with comprehensive SSRF protection.

    Security measures:
    - URL validation (HTTPS only, non-root path required)
    - DNS resolution with IP validation (prevents DNS rebinding)
    - Blocks private/loopback/link-local/multicast IPs
    - Response size limit (5KB max, enforced via streaming)
    - Redirects disabled (prevents redirect-based SSRF)
    - Overall timeout (prevents slow-stream DoS)
    """

    # Overall fetch timeout (seconds) - prevents slow-stream DoS
    FETCH_TIMEOUT = 30.0
    # Per-operation timeout (seconds)
    OPERATION_TIMEOUT = 10.0
    # Maximum response size (bytes)
    MAX_RESPONSE_SIZE = 5120  # 5KB

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
            timeout: HTTP request timeout in seconds (default 10.0)
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
        except (ValueError, AttributeError):
            return False

    async def _validate_url_and_resolve(self, url: str) -> tuple[str, int, list[str]]:
        """Validate URL format and resolve hostname to IPs with SSRF protection.

        This is the core SSRF protection. It:
        1. Validates URL format (HTTPS, has host, non-root path)
        2. Resolves hostname to IP addresses via DNS
        3. Validates ALL resolved IPs are allowed (public internet only)

        Args:
            url: URL to validate and resolve

        Returns:
            Tuple of (hostname, port, list of allowed IP addresses)

        Raises:
            CIMDValidationError: If validation fails or IPs are blocked
        """
        # Parse URL
        try:
            parsed = urlparse(url)
        except (ValueError, AttributeError) as e:
            raise CIMDValidationError(f"Invalid URL: {e}") from e

        # Require HTTPS
        if parsed.scheme != "https":
            raise CIMDValidationError(f"CIMD URLs must use HTTPS, got: {parsed.scheme}")

        # Require host
        if not parsed.netloc:
            raise CIMDValidationError("CIMD URLs must have a host")

        # Require non-root path
        if parsed.path in ("", "/"):
            raise CIMDValidationError(
                "CIMD URLs must have a non-root path (e.g., /client.json)"
            )

        hostname = parsed.hostname or parsed.netloc
        port = parsed.port or 443

        # Log non-standard ports
        if port != 443:
            logger.warning("CIMD URL uses non-standard port %d: %s", port, url)

        # Resolve hostname to IP addresses
        resolved_ips = await _resolve_hostname(hostname, port)

        # Validate ALL resolved IPs are allowed
        blocked_ips = [ip for ip in resolved_ips if not _is_ip_allowed(ip)]
        if blocked_ips:
            raise CIMDValidationError(
                f"CIMD URL resolves to blocked IP address(es): {blocked_ips}. "
                f"Private, loopback, link-local, and reserved IPs are not allowed."
            )

        return hostname, port, resolved_ips

    async def fetch(self, client_id_url: str) -> CIMDDocument:
        """Fetch and validate a CIMD document with comprehensive SSRF protection.

        Security measures:
        1. HTTPS only (no HTTP)
        2. DNS resolution with IP validation
        3. DNS pinning - connects to validated IP directly (prevents rebinding TOCTOU)
        4. Blocks private/loopback/link-local/multicast/reserved/RFC6598 IPs
        5. Response size limit (5KB, enforced via streaming)
        6. Redirects disabled (prevents redirect-based SSRF)
        7. Overall timeout (prevents slow-stream DoS)

        Args:
            client_id_url: The URL to fetch (also the expected client_id)

        Returns:
            Validated CIMDDocument

        Raises:
            CIMDValidationError: If document is invalid or URL blocked
            CIMDFetchError: If document cannot be fetched
        """
        # Track overall time to prevent slow-stream DoS
        start_time = time.monotonic()

        # Validate URL and resolve DNS with IP validation
        hostname, port, resolved_ips = await self._validate_url_and_resolve(
            client_id_url
        )

        # Log resolved IPs for debugging
        logger.debug("CIMD URL %s resolved to IPs: %s", client_id_url, resolved_ips)

        # Calculate remaining time budget
        elapsed = time.monotonic() - start_time
        remaining_timeout = max(1.0, self.FETCH_TIMEOUT - elapsed)

        # DNS Pinning: Connect to validated IP directly to prevent rebinding TOCTOU
        # This ensures httpx can't re-resolve DNS to a different (malicious) IP
        pinned_ip = resolved_ips[0]
        parsed = urlparse(client_id_url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        pinned_url = f"https://{format_ip_for_url(pinned_ip)}:{port}{path}"

        logger.debug(
            "DNS pinning: %s -> %s (connecting to %s)",
            client_id_url,
            pinned_url,
            pinned_ip,
        )

        # Fetch document with streaming to prevent memory exhaustion
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=min(self.timeout, remaining_timeout),
                        read=min(self.timeout, remaining_timeout),
                        write=min(self.timeout, remaining_timeout),
                        pool=min(self.timeout, remaining_timeout),
                    ),
                    follow_redirects=False,  # Disable redirects to prevent SSRF bypass
                    verify=True,  # Verify TLS against original hostname via SNI
                ) as client,
                client.stream(
                    "GET",
                    pinned_url,
                    headers={"Host": hostname},  # Set Host header for virtual hosting
                    extensions={
                        "sni_hostname": hostname
                    },  # TLS SNI for cert validation
                ) as response,
            ):
                # Check if we've exceeded overall timeout
                if time.monotonic() - start_time > self.FETCH_TIMEOUT:
                    raise CIMDFetchError(
                        f"Overall timeout exceeded fetching CIMD document: {client_id_url}"
                    )

                if response.status_code != 200:
                    raise CIMDFetchError(
                        f"CIMD document returned status {response.status_code}: {client_id_url}"
                    )

                # Check Content-Length header first if available
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > self.MAX_RESPONSE_SIZE:
                            raise CIMDFetchError(
                                f"Response too large: {size} bytes (max {self.MAX_RESPONSE_SIZE} bytes)"
                            )
                    except ValueError:
                        pass  # Invalid header, will check during streaming

                # Stream response with size and time limits
                chunks = []
                total_size = 0
                async for chunk in response.aiter_bytes():
                    # Check overall timeout
                    if time.monotonic() - start_time > self.FETCH_TIMEOUT:
                        raise CIMDFetchError(
                            f"Overall timeout exceeded while streaming CIMD document: {client_id_url}"
                        )

                    total_size += len(chunk)
                    if total_size > self.MAX_RESPONSE_SIZE:
                        raise CIMDFetchError(
                            f"Response too large: exceeded {self.MAX_RESPONSE_SIZE} bytes"
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
        except json.JSONDecodeError as e:
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

        # Validate jwks_uri if present (SSRF protection for JWKS fetch)
        if doc.jwks_uri:
            jwks_uri_str = str(doc.jwks_uri)
            # Must be HTTPS
            if not jwks_uri_str.startswith("https://"):
                raise CIMDValidationError(
                    f"CIMD jwks_uri must use HTTPS: {jwks_uri_str}"
                )
            # Validate and resolve to ensure it's not pointing to internal resources
            try:
                await self._validate_url_and_resolve(jwks_uri_str)
            except CIMDValidationError as e:
                raise CIMDValidationError(
                    f"CIMD jwks_uri failed validation: {e}"
                ) from e

        logger.info(
            "CIMD document fetched and validated: %s (client_name=%s)",
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

    JTI replay protection uses TTL-based caching to ensure proper security:
    - JTIs are cached with expiration matching the JWT's exp claim
    - Expired JTIs are automatically cleaned up
    - Maximum assertion lifetime is enforced (5 minutes)
    """

    # Maximum allowed assertion lifetime in seconds (RFC 7523 recommends short-lived)
    MAX_ASSERTION_LIFETIME = 300  # 5 minutes

    def __init__(self):
        # JTI cache: maps jti -> expiration timestamp
        self._jti_cache: dict[str, float] = {}
        self._jti_cache_max_size = 10000
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 60  # Cleanup every 60 seconds
        self.logger = get_logger(__name__)

    def _cleanup_expired_jtis(self) -> None:
        """Remove expired JTIs from cache."""
        now = time.time()
        expired = [jti for jti, exp in self._jti_cache.items() if exp < now]
        for jti in expired:
            del self._jti_cache[jti]
        if expired:
            self.logger.debug("Cleaned up %d expired JTIs from cache", len(expired))

    def _maybe_cleanup(self) -> None:
        """Periodically cleanup expired JTIs to prevent unbounded growth."""
        now = time.monotonic()
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired_jtis()
            self._last_cleanup = now

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

        # Periodic cleanup of expired JTIs
        self._maybe_cleanup()

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

        # 3. Validate assertion lifetime (exp and iat)
        now = time.time()
        exp = claims.get("exp")
        iat = claims.get("iat")

        if not exp:
            raise ValueError("Assertion must include exp claim")

        # Validate exp is in the future (with small clock skew tolerance)
        if exp < now - 30:  # 30 second clock skew tolerance
            raise ValueError("Assertion has expired")

        # If iat is present, validate it and check assertion lifetime
        if iat:
            if iat > now + 30:  # 30 second clock skew tolerance
                raise ValueError("Assertion iat is in the future")
            if exp - iat > self.MAX_ASSERTION_LIFETIME:
                raise ValueError(
                    f"Assertion lifetime too long: {exp - iat}s (max {self.MAX_ASSERTION_LIFETIME}s)"
                )
        else:
            # No iat, enforce max lifetime from now
            if exp > now + self.MAX_ASSERTION_LIFETIME:
                raise ValueError(
                    f"Assertion exp too far in future (max {self.MAX_ASSERTION_LIFETIME}s)"
                )

        # 4. Additional RFC 7523 validation: sub claim must equal client_id
        if claims.get("sub") != client_id:
            raise ValueError(f"Assertion sub claim must be {client_id}")

        # 5. Check jti for replay attacks (RFC 7523 requirement)
        jti = claims.get("jti")
        if not jti:
            raise ValueError("Assertion must include jti claim")

        # Check if JTI was already used (and hasn't expired from cache)
        if jti in self._jti_cache:
            cached_exp = self._jti_cache[jti]
            if cached_exp > now:  # Still valid in cache
                raise ValueError(f"Assertion replay detected: jti {jti} already used")
            # Expired in cache, can be reused (clean it up)
            del self._jti_cache[jti]

        # Add to cache with expiration time
        # Use the assertion's exp claim so it stays cached until it would expire anyway
        self._jti_cache[jti] = exp

        # Emergency size limit (shouldn't hit with proper TTL cleanup)
        if len(self._jti_cache) > self._jti_cache_max_size:
            self._cleanup_expired_jtis()
            # If still over limit after cleanup, reject to prevent DoS
            if len(self._jti_cache) > self._jti_cache_max_size:
                self.logger.warning(
                    "JTI cache at max capacity (%d), possible attack",
                    self._jti_cache_max_size,
                )
                raise ValueError("Server overloaded, please retry")

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
