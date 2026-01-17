"""Tests for CIMD SSRF protection and security hardening.

This module tests the security measures implemented to prevent SSRF attacks
in CIMD document fetching:

1. Private IP address and hostname blocking (via DNS resolution validation)
2. Response size limits via streaming (5KB max)
3. HTTP redirect blocking
4. HTTPS requirement
5. Redirect URI validation using proxy's allowed patterns
6. Non-standard port handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import AnyHttpUrl

from fastmcp.server.auth.cimd import (
    CIMDClientManager,
    CIMDDocument,
    CIMDFetcher,
    CIMDFetchError,
    CIMDValidationError,
    _is_ip_allowed,
)


class TestIPAllowedFunction:
    """Tests for the _is_ip_allowed function directly."""

    def test_private_ipv4_blocked(self):
        """Private IPv4 addresses should be blocked."""
        assert _is_ip_allowed("192.168.1.1") is False
        assert _is_ip_allowed("10.0.0.1") is False
        assert _is_ip_allowed("172.16.0.1") is False
        assert _is_ip_allowed("172.31.255.255") is False

    def test_loopback_blocked(self):
        """Loopback addresses should be blocked."""
        assert _is_ip_allowed("127.0.0.1") is False
        assert _is_ip_allowed("127.0.0.255") is False
        assert _is_ip_allowed("::1") is False

    def test_link_local_blocked(self):
        """Link-local addresses (AWS metadata!) should be blocked."""
        assert _is_ip_allowed("169.254.169.254") is False  # AWS metadata
        assert _is_ip_allowed("169.254.0.1") is False

    def test_multicast_blocked(self):
        """Multicast addresses should be blocked."""
        assert _is_ip_allowed("224.0.0.1") is False
        assert _is_ip_allowed("239.255.255.255") is False

    def test_unspecified_blocked(self):
        """Unspecified addresses should be blocked."""
        assert _is_ip_allowed("0.0.0.0") is False
        assert _is_ip_allowed("::") is False

    def test_public_ipv4_allowed(self):
        """Public IPv4 addresses should be allowed."""
        assert _is_ip_allowed("8.8.8.8") is True
        assert _is_ip_allowed("1.1.1.1") is True
        assert _is_ip_allowed("93.184.216.34") is True  # example.com

    def test_ipv4_mapped_ipv6_blocked_if_private(self):
        """IPv4-mapped IPv6 addresses should be validated for the inner IPv4."""
        assert _is_ip_allowed("::ffff:127.0.0.1") is False
        assert _is_ip_allowed("::ffff:192.168.1.1") is False

    def test_invalid_ip_blocked(self):
        """Invalid IP strings should be blocked."""
        assert _is_ip_allowed("not-an-ip") is False
        assert _is_ip_allowed("") is False


class TestSSRFHostnameBlocking:
    """Tests for blocking private/loopback hostnames via DNS resolution."""

    async def test_private_ip_hostname_rejected(self):
        """Hostnames that resolve to private IPs should be rejected."""
        fetcher = CIMDFetcher()

        # Mock DNS resolution to return a private IP
        with patch(
            "fastmcp.server.auth.cimd._resolve_hostname",
            return_value=["192.168.1.1"],
        ):
            with pytest.raises(CIMDValidationError, match="blocked IP"):
                await fetcher.fetch("https://example.com/client.json")

    async def test_localhost_hostname_rejected(self):
        """Localhost hostnames should be rejected."""
        fetcher = CIMDFetcher()

        # Mock DNS resolution to return loopback
        with patch(
            "fastmcp.server.auth.cimd._resolve_hostname",
            return_value=["127.0.0.1"],
        ):
            with pytest.raises(CIMDValidationError, match="blocked IP"):
                await fetcher.fetch("https://localhost/client.json")

    async def test_loopback_hostname_rejected(self):
        """Loopback addresses should be rejected."""
        fetcher = CIMDFetcher()

        with patch(
            "fastmcp.server.auth.cimd._resolve_hostname",
            return_value=["127.0.0.1"],
        ):
            with pytest.raises(CIMDValidationError, match="blocked IP"):
                await fetcher.fetch("https://loopback.example.com/client.json")

    async def test_internal_hostname_patterns_rejected(self):
        """Hostnames resolving to internal IPs should be rejected."""
        fetcher = CIMDFetcher()

        # Test various private IP ranges
        private_ips = [
            "192.168.0.1",
            "10.0.0.1",
            "172.16.0.1",
        ]

        for private_ip in private_ips:
            with patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=[private_ip],
            ):
                with pytest.raises(CIMDValidationError, match="blocked IP"):
                    await fetcher.fetch("https://internal.example.com/client.json")

    async def test_link_local_ip_rejected(self):
        """Link-local IPs (AWS metadata endpoint) should be rejected."""
        fetcher = CIMDFetcher()

        with patch(
            "fastmcp.server.auth.cimd._resolve_hostname",
            return_value=["169.254.169.254"],  # AWS metadata
        ):
            with pytest.raises(CIMDValidationError, match="blocked IP"):
                await fetcher.fetch("https://metadata.example.com/client.json")

    async def test_dns_rebinding_prevented(self):
        """DNS rebinding attack should be prevented by validating resolved IPs."""
        fetcher = CIMDFetcher()

        # Attacker's DNS returns private IP (simulating DNS rebinding)
        with patch(
            "fastmcp.server.auth.cimd._resolve_hostname",
            return_value=["127.0.0.1"],
        ):
            with pytest.raises(CIMDValidationError, match="blocked IP"):
                await fetcher.fetch("https://attacker.com/client.json")


class TestSSRFResponseSizeLimits:
    """Tests for response size limits via streaming to prevent DoS."""

    async def test_response_size_limit_via_content_length_header(self):
        """Responses with Content-Length > 5KB should be rejected before download."""
        fetcher = CIMDFetcher()

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=["93.184.216.34"],  # Public IP
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": "10240"}  # 10KB
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            with pytest.raises(CIMDFetchError, match="Response too large"):
                await fetcher.fetch("https://example.com/client.json")

    async def test_response_size_limit_via_streaming(self):
        """Responses exceeding 5KB during streaming should be aborted."""
        fetcher = CIMDFetcher()

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=["93.184.216.34"],  # Public IP
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Create a mock stream that yields chunks
            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {}  # No content-length header
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            # Simulate streaming large chunks that exceed 5KB
            async def aiter_bytes():
                # Yield 10KB total in 1KB chunks
                for _ in range(10):
                    yield b"x" * 1024

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            with pytest.raises(CIMDFetchError, match="Response too large"):
                await fetcher.fetch("https://example.com/client.json")

    async def test_response_within_size_limit_accepted(self):
        """Responses under 5KB should be accepted."""
        fetcher = CIMDFetcher()

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=["93.184.216.34"],  # Public IP
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Create valid CIMD document
            doc_content = b"""{
                "client_id": "https://example.com/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            # Should not raise
            doc = await fetcher.fetch("https://example.com/client.json")
            assert str(doc.client_id) == "https://example.com/client.json"


class TestSSRFRedirectPrevention:
    """Tests for HTTP redirect blocking."""

    async def test_redirects_disabled(self):
        """HTTP redirects should be disabled to prevent redirect-based SSRF."""
        fetcher = CIMDFetcher()

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=["93.184.216.34"],  # Public IP
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Verify follow_redirects=False is passed
            mock_stream = MagicMock()
            mock_stream.__aenter__ = AsyncMock(side_effect=httpx.RequestError("test"))

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            try:
                await fetcher.fetch("https://example.com/client.json")
            except CIMDFetchError:
                pass

            # Verify AsyncClient was created with follow_redirects=False
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs["follow_redirects"] is False


class TestCIMDRedirectURIValidation:
    """Tests for CIMD redirect URI validation using proxy's allowed patterns."""

    async def test_cimd_uses_proxy_redirect_patterns(self):
        """CIMD clients should validate redirect URIs against proxy's allowed_client_redirect_uris."""
        manager = CIMDClientManager(
            enable_cimd=True,
            default_scope="profile",
            allowed_redirect_uri_patterns=["http://localhost:*"],
        )

        # Mock the fetcher to return a CIMD document
        mock_doc = CIMDDocument(
            client_id=AnyHttpUrl("https://example.com/client.json"),
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
            redirect_uris=[
                "https://example.com/callback"
            ],  # Document specifies different URIs
        )

        with patch.object(manager._fetcher, "fetch", return_value=mock_doc):
            client = await manager.get_client("https://example.com/client.json")

            # Verify client uses proxy's patterns, NOT the document's redirect_uris
            assert client is not None
            assert client.allowed_redirect_uri_patterns == ["http://localhost:*"]
            assert client.allowed_redirect_uri_patterns != mock_doc.redirect_uris

    async def test_cimd_redirect_uris_are_documentation_only(self):
        """CIMD document redirect_uris should not override proxy configuration."""
        # Manager with restrictive patterns
        manager = CIMDClientManager(
            enable_cimd=True,
            allowed_redirect_uri_patterns=["http://127.0.0.1:*"],
        )

        # CIMD document claims broader redirect URIs
        mock_doc = CIMDDocument(
            client_id=AnyHttpUrl("https://example.com/client.json"),
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
            redirect_uris=[
                "https://evil.com/steal-tokens"
            ],  # Attacker's URL in document
        )

        with patch.object(manager._fetcher, "fetch", return_value=mock_doc):
            client = await manager.get_client("https://example.com/client.json")

            # Client should use proxy's restrictive patterns
            assert client.allowed_redirect_uri_patterns == ["http://127.0.0.1:*"]

            # Verify the document's redirect_uris are stored but not used for validation
            assert (
                str(client.cimd_document.redirect_uris[0])
                == "https://evil.com/steal-tokens"
            )
            assert client.allowed_redirect_uri_patterns != [
                str(uri) for uri in client.cimd_document.redirect_uris
            ]

    async def test_cimd_with_none_redirect_patterns_allows_all(self):
        """CIMD clients with None patterns should allow all redirect URIs (DCR compatibility)."""
        manager = CIMDClientManager(
            enable_cimd=True,
            allowed_redirect_uri_patterns=None,  # Allow all
        )

        mock_doc = CIMDDocument(
            client_id=AnyHttpUrl("https://example.com/client.json"),
            grant_types=["authorization_code"],
            token_endpoint_auth_method="none",
        )

        with patch.object(manager._fetcher, "fetch", return_value=mock_doc):
            client = await manager.get_client("https://example.com/client.json")

            # Should be None (allow all)
            assert client.allowed_redirect_uri_patterns is None


class TestSSRFURLValidation:
    """Tests for basic URL validation."""

    async def test_non_https_url_rejected(self):
        """Non-HTTPS URLs should be rejected."""
        fetcher = CIMDFetcher()

        with pytest.raises(CIMDValidationError, match="must use HTTPS"):
            await fetcher.fetch("http://example.com/client.json")

    async def test_root_path_rejected(self):
        """URLs with root path should be rejected."""
        fetcher = CIMDFetcher()

        with pytest.raises(CIMDValidationError, match="non-root path"):
            await fetcher.fetch("https://example.com/")

    async def test_empty_path_rejected(self):
        """URLs with empty path should be rejected."""
        fetcher = CIMDFetcher()

        with pytest.raises(CIMDValidationError, match="non-root path"):
            await fetcher.fetch("https://example.com")


class TestSSRFPortHandling:
    """Tests for non-standard port handling."""

    async def test_non_standard_port_allowed(self):
        """Non-standard HTTPS ports should be allowed (warning logged visually)."""
        fetcher = CIMDFetcher()

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=["93.184.216.34"],  # Public IP
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Create valid CIMD document
            doc_content = b"""{
                "client_id": "https://example.com:8443/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            # Should succeed (warning logged but not testable via caplog due to Rich output)
            doc = await fetcher.fetch("https://example.com:8443/client.json")
            assert str(doc.client_id) == "https://example.com:8443/client.json"

    async def test_standard_port_443_no_warning(self):
        """Standard HTTPS port (443) should not trigger warnings."""
        fetcher = CIMDFetcher()

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=["93.184.216.34"],  # Public IP
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Create valid CIMD document
            doc_content = b"""{
                "client_id": "https://example.com/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            # Should succeed without any port-related warnings
            doc = await fetcher.fetch("https://example.com/client.json")
            assert str(doc.client_id) == "https://example.com/client.json"


class TestRFC6598CarrierGradeNAT:
    """Tests for RFC6598 Carrier-Grade NAT (100.64.0.0/10) blocking."""

    def test_rfc6598_cgnat_blocked(self):
        """RFC6598 Carrier-Grade NAT addresses should be blocked."""
        # These are in the 100.64.0.0/10 range used for carrier-grade NAT
        # They can point to internal infrastructure and should be blocked
        assert _is_ip_allowed("100.64.0.1") is False
        assert _is_ip_allowed("100.64.255.255") is False
        assert _is_ip_allowed("100.100.100.100") is False
        assert _is_ip_allowed("100.127.255.255") is False

    def test_public_ips_in_100_range_outside_cgnat_allowed(self):
        """IPs in 100.x range outside CGNAT (100.64-127) should be allowed."""
        # 100.0.0.0 - 100.63.255.255 are normal public IPs
        assert _is_ip_allowed("100.0.0.1") is True
        assert _is_ip_allowed("100.63.255.255") is True
        # 100.128.0.0 - 100.255.255.255 are normal public IPs
        assert _is_ip_allowed("100.128.0.1") is True

    async def test_dns_resolving_to_rfc6598_rejected(self):
        """Hostnames resolving to RFC6598 addresses should be rejected."""
        fetcher = CIMDFetcher()

        with patch(
            "fastmcp.server.auth.cimd._resolve_hostname",
            return_value=["100.64.0.1"],
        ):
            with pytest.raises(CIMDValidationError, match="blocked IP"):
                await fetcher.fetch("https://cgnat.example.com/client.json")


class TestDNSPinning:
    """Tests for DNS pinning to prevent TOCTOU attacks."""

    async def test_connects_to_pinned_ip(self):
        """Verify that httpx connects to the pinned IP, not re-resolving DNS."""
        fetcher = CIMDFetcher()

        # Resolve to a public IP
        resolved_ip = "93.184.216.34"

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=[resolved_ip],
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Create valid CIMD document
            doc_content = b"""{
                "client_id": "https://example.com/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            await fetcher.fetch("https://example.com/client.json")

            # Verify the URL passed to stream() contains the pinned IP
            mock_client.stream.assert_called_once()
            call_args = mock_client.stream.call_args
            url_called = call_args[0][1]  # Second positional arg is the URL

            # The URL should be using the pinned IP
            assert resolved_ip in url_called, (
                f"Expected pinned IP {resolved_ip} in URL, got {url_called}"
            )

    async def test_dns_pinning_sets_host_header(self):
        """Verify Host header is set to original hostname when connecting to IP."""
        fetcher = CIMDFetcher()

        resolved_ip = "93.184.216.34"
        original_host = "example.com"

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=[resolved_ip],
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            doc_content = b"""{
                "client_id": "https://example.com/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            await fetcher.fetch(f"https://{original_host}/client.json")

            # Verify Host header is set to original hostname
            call_kwargs = mock_client.stream.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert headers.get("Host") == original_host

    async def test_dns_pinning_sets_sni_hostname(self):
        """Verify SNI hostname extension is set for TLS verification."""
        fetcher = CIMDFetcher()

        resolved_ip = "93.184.216.34"
        original_host = "example.com"

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=[resolved_ip],
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            doc_content = b"""{
                "client_id": "https://example.com/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            await fetcher.fetch(f"https://{original_host}/client.json")

            # Verify SNI hostname extension is set
            call_kwargs = mock_client.stream.call_args[1]
            extensions = call_kwargs.get("extensions", {})
            assert extensions.get("sni_hostname") == original_host


class TestIPv6URLFormatting:
    """Tests for proper IPv6 address bracketing in URLs."""

    def test_format_ip_for_url_ipv4(self):
        """IPv4 addresses should not be bracketed."""
        from fastmcp.server.auth.ssrf import format_ip_for_url

        assert format_ip_for_url("8.8.8.8") == "8.8.8.8"
        assert format_ip_for_url("192.168.1.1") == "192.168.1.1"

    def test_format_ip_for_url_ipv6(self):
        """IPv6 addresses should be bracketed for URL use."""
        from fastmcp.server.auth.ssrf import format_ip_for_url

        assert format_ip_for_url("2001:db8::1") == "[2001:db8::1]"
        assert format_ip_for_url("::1") == "[::1]"
        assert format_ip_for_url("fe80::1") == "[fe80::1]"

    def test_format_ip_for_url_invalid(self):
        """Invalid IP strings should be returned unchanged."""
        from fastmcp.server.auth.ssrf import format_ip_for_url

        assert format_ip_for_url("not-an-ip") == "not-an-ip"
        assert format_ip_for_url("") == ""

    async def test_ipv6_pinned_url_is_valid(self):
        """Verify IPv6 addresses are properly bracketed in pinned URLs."""
        fetcher = CIMDFetcher()

        # Use a public IPv6 address (Google DNS)
        resolved_ipv6 = "2001:4860:4860::8888"

        with (
            patch(
                "fastmcp.server.auth.cimd._resolve_hostname",
                return_value=[resolved_ipv6],
            ),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            doc_content = b"""{
                "client_id": "https://example.com/client.json",
                "grant_types": ["authorization_code"],
                "token_endpoint_auth_method": "none"
            }"""

            mock_stream = MagicMock()
            mock_stream.status_code = 200
            mock_stream.headers = {"content-length": str(len(doc_content))}
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock(return_value=None)

            async def aiter_bytes():
                yield doc_content

            mock_stream.aiter_bytes = aiter_bytes

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_stream)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            await fetcher.fetch("https://example.com/client.json")

            # Verify the URL contains bracketed IPv6 address
            call_args = mock_client.stream.call_args
            url_called = call_args[0][1]

            # IPv6 should be bracketed: https://[2001:4860:4860::8888]:443/path
            assert f"[{resolved_ipv6}]" in url_called, (
                f"Expected bracketed IPv6 [{resolved_ipv6}] in URL, got {url_called}"
            )
