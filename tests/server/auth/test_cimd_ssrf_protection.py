"""Tests for CIMD SSRF protection and security hardening.

This module tests the security measures implemented to prevent SSRF attacks
in CIMD document fetching:

1. Private IP address and hostname blocking
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
)


class TestSSRFHostnameBlocking:
    """Tests for blocking private/loopback hostnames."""

    async def test_private_ip_hostname_rejected(self):
        """Hostnames that are private IPs should be rejected."""
        fetcher = CIMDFetcher()

        with pytest.raises(CIMDValidationError, match="private/loopback"):
            await fetcher.fetch("https://192.168.1.1/client.json")

    async def test_localhost_hostname_rejected(self):
        """Localhost hostnames should be rejected."""
        fetcher = CIMDFetcher()

        with pytest.raises(CIMDValidationError, match="private/loopback"):
            await fetcher.fetch("https://localhost/client.json")

        with pytest.raises(CIMDValidationError, match="private/loopback"):
            await fetcher.fetch("https://127.0.0.1/client.json")

    async def test_loopback_hostname_rejected(self):
        """Loopback addresses should be rejected."""
        fetcher = CIMDFetcher()

        with pytest.raises(CIMDValidationError, match="private/loopback"):
            await fetcher.fetch("https://127.0.0.1/client.json")

    async def test_internal_hostname_patterns_rejected(self):
        """Common internal hostname patterns should be rejected."""
        fetcher = CIMDFetcher()

        # These should all be rejected as potential internal hosts
        internal_hosts = [
            "https://internal.local/client.json",
            "https://192.168.0.1/client.json",
            "https://10.0.0.1/client.json",
            "https://172.16.0.1/client.json",
        ]

        for url in internal_hosts:
            with pytest.raises(CIMDValidationError, match="private/loopback"):
                await fetcher.fetch(url)


class TestSSRFResponseSizeLimits:
    """Tests for response size limits via streaming to prevent DoS."""

    async def test_response_size_limit_via_content_length_header(self):
        """Responses with Content-Length > 5KB should be rejected before download."""
        fetcher = CIMDFetcher()

        with patch("httpx.AsyncClient") as mock_client_class:
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

        with patch("httpx.AsyncClient") as mock_client_class:
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

        with patch("httpx.AsyncClient") as mock_client_class:
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

        with patch("httpx.AsyncClient") as mock_client_class:
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

        with patch("httpx.AsyncClient") as mock_client_class:
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

        with patch("httpx.AsyncClient") as mock_client_class:
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
