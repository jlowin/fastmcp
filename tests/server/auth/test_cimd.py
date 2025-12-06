"""Tests for CIMD (Client ID Metadata Document) support per SEP-991."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from pytest_httpx import HTTPXMock

from fastmcp.server.auth._cimd import (
    _CIMDCache,
    _create_client_from_metadata,
    _fetch_client_metadata,
    _get_cimd_client,
    _is_cimd_client_id,
    _is_private_ip,
    _validate_cimd_url,
)
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider


class TestIsCimdClientId:
    """Test _is_cimd_client_id function."""

    def test_valid_https_with_path(self):
        assert _is_cimd_client_id("https://example.com/oauth/client.json") is True
        assert _is_cimd_client_id("https://app.example.com/metadata") is True
        assert _is_cimd_client_id("https://example.com/a") is True

    def test_rejects_http(self):
        assert _is_cimd_client_id("http://example.com/oauth/client.json") is False

    def test_rejects_root_path(self):
        assert _is_cimd_client_id("https://example.com") is False
        assert _is_cimd_client_id("https://example.com/") is False

    def test_rejects_non_url(self):
        assert _is_cimd_client_id("not-a-url") is False
        assert _is_cimd_client_id("client-id-123") is False
        assert _is_cimd_client_id("") is False

    def test_rejects_non_string(self):
        assert _is_cimd_client_id(123) is False  # type: ignore[arg-type]
        assert _is_cimd_client_id(None) is False  # type: ignore[arg-type]


class TestIsPrivateIp:
    """Test _is_private_ip function."""

    def test_private_ipv4_10_x(self):
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("10.255.255.255") is True

    def test_private_ipv4_172_16_x(self):
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True
        # 172.15.x and 172.32.x are NOT private
        assert _is_private_ip("172.15.0.1") is False
        assert _is_private_ip("172.32.0.1") is False

    def test_private_ipv4_192_168_x(self):
        assert _is_private_ip("192.168.0.1") is True
        assert _is_private_ip("192.168.255.255") is True

    def test_localhost(self):
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("127.0.0.2") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.0.1") is True
        assert _is_private_ip("169.254.255.255") is True

    def test_public_ipv4(self):
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False
        assert _is_private_ip("93.184.216.34") is False  # example.com

    def test_ipv6_loopback(self):
        assert _is_private_ip("::1") is True

    def test_invalid_ip(self):
        # Invalid IPs are treated as suspicious (returns True)
        assert _is_private_ip("not-an-ip") is True


class TestValidateCimdUrl:
    """Test _validate_cimd_url function."""

    def test_requires_https(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            _validate_cimd_url("http://example.com/metadata")

    def test_requires_non_root_path(self):
        with pytest.raises(ValueError, match="non-root path"):
            _validate_cimd_url("https://example.com")
        with pytest.raises(ValueError, match="non-root path"):
            _validate_cimd_url("https://example.com/")

    def test_rejects_private_ip(self):
        # Mock DNS resolution to return private IP
        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("example.com", [], ["10.0.0.1"])
            with pytest.raises(ValueError, match="private IP"):
                _validate_cimd_url("https://internal.example.com/metadata")

    def test_accepts_public_ip(self):
        # Mock DNS resolution to return public IP
        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("example.com", [], ["93.184.216.34"])
            # Should not raise
            _validate_cimd_url("https://example.com/metadata")


class TestFetchClientMetadata:
    """Test _fetch_client_metadata function."""

    async def test_fetch_success(self, httpx_mock: HTTPXMock):
        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
        }

        # Mock DNS to return public IP
        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("client.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, json=metadata)

            result = await _fetch_client_metadata(client_id)

        assert result == metadata

    async def test_fetch_timeout(self, httpx_mock: HTTPXMock):
        import httpx

        client_id = "https://slow.example.com/metadata.json"

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("slow.example.com", [], ["93.184.216.34"])
            httpx_mock.add_exception(httpx.TimeoutException("Connection timed out"))

            with pytest.raises(httpx.TimeoutException):
                await _fetch_client_metadata(client_id, timeout=0.1)

    async def test_fetch_size_limit_via_header(self, httpx_mock: HTTPXMock):
        client_id = "https://large.example.com/metadata.json"

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("large.example.com", [], ["93.184.216.34"])
            # Return a response with content-length exceeding limit
            httpx_mock.add_response(
                url=client_id,
                json={"client_id": client_id},
                headers={"content-length": "2000000"},  # 2MB
            )

            with pytest.raises(ValueError, match="too large"):
                await _fetch_client_metadata(client_id, max_size=1_048_576)

    async def test_fetch_invalid_json(self, httpx_mock: HTTPXMock):
        client_id = "https://bad.example.com/metadata.json"

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("bad.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, text="not json {{{")

            with pytest.raises(Exception):  # JSONDecodeError
                await _fetch_client_metadata(client_id)


class TestCreateClientFromMetadata:
    """Test _create_client_from_metadata function."""

    def test_creates_client_from_valid_metadata(self):
        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        }

        result = _create_client_from_metadata(client_id, metadata)

        assert isinstance(result, OAuthClientInformationFull)
        assert result.client_id == client_id
        assert result.client_name == "Test Client"
        assert result.token_endpoint_auth_method == "none"

    def test_defaults_token_endpoint_auth_method_to_none(self):
        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            # No token_endpoint_auth_method specified
        }

        result = _create_client_from_metadata(client_id, metadata)
        assert result.token_endpoint_auth_method == "none"

    def test_rejects_mismatched_client_id(self):
        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": "https://other.example.com/different.json",
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
        }

        with pytest.raises(ValueError, match="doesn't match"):
            _create_client_from_metadata(client_id, metadata)


class TestCIMDCache:
    """Test _CIMDCache class."""

    def test_cache_hit(self):
        cache = _CIMDCache()
        client_id = "https://client.example.com/metadata.json"
        client_info = OAuthClientInformationFull(
            client_id=client_id,
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        )

        cache.set(client_id, client_info)
        result = cache.get(client_id)

        assert result is not None
        assert result.client_id == client_id

    def test_cache_miss(self):
        cache = _CIMDCache()
        result = cache.get("https://unknown.example.com/metadata.json")
        assert result is None

    def test_cache_expiry(self):
        cache = _CIMDCache(default_ttl=1)  # 1 second TTL
        client_id = "https://client.example.com/metadata.json"
        client_info = OAuthClientInformationFull(
            client_id=client_id,
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        )

        cache.set(client_id, client_info, ttl=1)

        # Should be in cache
        assert cache.get(client_id) is not None

        # Wait for expiry
        time.sleep(1.1)

        # Should be expired
        assert cache.get(client_id) is None

    def test_cache_respects_max_ttl(self):
        cache = _CIMDCache(default_ttl=3600, max_ttl=2)  # 2 second max
        client_id = "https://client.example.com/metadata.json"
        client_info = OAuthClientInformationFull(
            client_id=client_id,
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        )

        # Try to set with 1 hour TTL, should be capped to 2 seconds
        cache.set(client_id, client_info, ttl=3600)

        # Should be in cache
        assert cache.get(client_id) is not None

        # Wait longer than max_ttl
        time.sleep(2.1)

        # Should be expired due to max_ttl cap
        assert cache.get(client_id) is None

    def test_cache_clear(self):
        cache = _CIMDCache()
        client_id = "https://client.example.com/metadata.json"
        client_info = OAuthClientInformationFull(
            client_id=client_id,
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        )

        cache.set(client_id, client_info)
        assert cache.get(client_id) is not None

        cache.clear()
        assert cache.get(client_id) is None


class TestGetCimdClient:
    """Test _get_cimd_client function."""

    async def test_fetches_and_validates(self, httpx_mock: HTTPXMock):
        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
        }

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("client.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, json=metadata)

            result = await _get_cimd_client(client_id)

        assert isinstance(result, OAuthClientInformationFull)
        assert result.client_id == client_id

    async def test_uses_cache(self, httpx_mock: HTTPXMock):
        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
        }

        cache = _CIMDCache()

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("client.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, json=metadata)

            # First call - should fetch
            result1 = await _get_cimd_client(client_id, cache=cache)

            # Second call - should use cache (no HTTP request)
            result2 = await _get_cimd_client(client_id, cache=cache)

        assert result1.client_id == client_id
        assert result2.client_id == client_id

        # Verify only one HTTP request was made
        assert len(httpx_mock.get_requests()) == 1


class TestOAuthProviderCIMD:
    """Test CIMD integration in OAuthProvider base class."""

    async def test_lookup_cimd_client_returns_none_for_non_url(self):
        """CIMD lookup should return None for non-URL client_ids."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")

        result = await provider._lookup_cimd_client("regular-client-id")
        assert result is None

    async def test_lookup_cimd_client_returns_none_when_disabled(self):
        """CIMD lookup should return None when cimd_enabled=False."""
        provider = InMemoryOAuthProvider(
            base_url="http://localhost:8000",
        )
        provider._cimd_enabled = False

        result = await provider._lookup_cimd_client(
            "https://client.example.com/metadata.json"
        )
        assert result is None

    async def test_lookup_cimd_client_success(self, httpx_mock: HTTPXMock):
        """CIMD lookup should successfully fetch and return client info."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")

        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
        }

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("client.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, json=metadata)

            result = await provider._lookup_cimd_client(client_id)

        assert result is not None
        assert result.client_id == client_id

    async def test_lookup_cimd_client_returns_none_on_error(
        self, httpx_mock: HTTPXMock
    ):
        """CIMD lookup should return None and log on error, not raise."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")

        client_id = "https://failing.example.com/metadata.json"

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("failing.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, status_code=404)

            result = await provider._lookup_cimd_client(client_id)

        assert result is None


class TestInMemoryProviderCIMD:
    """Test CIMD integration in InMemoryOAuthProvider."""

    async def test_get_client_uses_cimd_for_url(self, httpx_mock: HTTPXMock):
        """get_client should use CIMD for URL-based client_ids."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")

        client_id = "https://client.example.com/metadata.json"
        metadata = {
            "client_id": client_id,
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
        }

        with patch("socket.gethostbyname_ex") as mock_dns:
            mock_dns.return_value = ("client.example.com", [], ["93.184.216.34"])
            httpx_mock.add_response(url=client_id, json=metadata)

            result = await provider.get_client(client_id)

        assert result is not None
        assert result.client_id == client_id

    async def test_get_client_uses_registered_for_non_url(self):
        """get_client should use registered clients for non-URL client_ids."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")

        # Register a client
        client_info = OAuthClientInformationFull(
            client_id="regular-client-id",
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        )
        await provider.register_client(client_info)

        result = await provider.get_client("regular-client-id")

        assert result is not None
        assert result.client_id == "regular-client-id"

    async def test_get_client_returns_none_for_unknown(self):
        """get_client should return None for unknown non-URL client_ids."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")

        result = await provider.get_client("unknown-client-id")
        assert result is None


class TestOAuthMetadataAdvertisesCIMD:
    """Test that OAuth metadata advertises CIMD support."""

    def test_cimd_enabled_by_default(self):
        """CIMD should be enabled by default."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")
        assert provider._cimd_enabled is True
        assert provider._cimd_cache is not None

    def test_cimd_can_be_disabled(self):
        """CIMD can be disabled via constructor parameter."""
        provider = InMemoryOAuthProvider(base_url="http://localhost:8000")
        provider._cimd_enabled = False
        # Note: We can't easily test the full disable path without
        # exposing cimd_enabled in InMemoryOAuthProvider's __init__
