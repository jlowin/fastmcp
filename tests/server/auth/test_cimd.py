"""Unit tests for CIMD (Client ID Metadata Document) functionality."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from fastmcp.server.auth.cimd import (
    CIMDDocument,
    CIMDFetchError,
    CIMDFetcher,
    CIMDTrustPolicy,
    CIMDValidationError,
    DEFAULT_TRUSTED_CIMD_DOMAINS,
)


class TestCIMDDocument:
    """Tests for CIMDDocument model validation."""

    def test_valid_minimal_document(self):
        """Test that minimal valid document passes validation."""
        doc = CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
        )
        assert str(doc.client_id) == "https://example.com/client.json"
        assert doc.token_endpoint_auth_method == "none"
        assert doc.grant_types == ["authorization_code"]
        assert doc.response_types == ["code"]

    def test_valid_full_document(self):
        """Test that full document passes validation."""
        doc = CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            client_name="My App",
            client_uri="https://example.com",  # type: ignore[arg-type]
            logo_uri="https://example.com/logo.png",  # type: ignore[arg-type]
            redirect_uris=["http://localhost:3000/callback"],
            token_endpoint_auth_method="none",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="read write",
        )
        assert doc.client_name == "My App"
        assert doc.scope == "read write"

    def test_private_key_jwt_auth_method_allowed(self):
        """Test that private_key_jwt is allowed for CIMD."""
        doc = CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            token_endpoint_auth_method="private_key_jwt",
            jwks_uri="https://example.com/.well-known/jwks.json",  # type: ignore[arg-type]
        )
        assert doc.token_endpoint_auth_method == "private_key_jwt"

    def test_client_secret_basic_rejected(self):
        """Test that client_secret_basic is rejected for CIMD."""
        with pytest.raises(ValidationError) as exc_info:
            CIMDDocument(
                client_id="https://example.com/client.json",  # type: ignore[arg-type]
                token_endpoint_auth_method="client_secret_basic",  # type: ignore[arg-type]
            )
        # Literal type rejects invalid values before custom validator
        assert "token_endpoint_auth_method" in str(exc_info.value)

    def test_client_secret_post_rejected(self):
        """Test that client_secret_post is rejected for CIMD."""
        with pytest.raises(ValidationError) as exc_info:
            CIMDDocument(
                client_id="https://example.com/client.json",  # type: ignore[arg-type]
                token_endpoint_auth_method="client_secret_post",  # type: ignore[arg-type]
            )
        assert "token_endpoint_auth_method" in str(exc_info.value)

    def test_client_secret_jwt_rejected(self):
        """Test that client_secret_jwt is rejected for CIMD."""
        with pytest.raises(ValidationError) as exc_info:
            CIMDDocument(
                client_id="https://example.com/client.json",  # type: ignore[arg-type]
                token_endpoint_auth_method="client_secret_jwt",  # type: ignore[arg-type]
            )
        assert "token_endpoint_auth_method" in str(exc_info.value)


class TestCIMDTrustPolicy:
    """Tests for CIMDTrustPolicy."""

    def test_default_trusted_domains(self):
        """Test that default trusted domains are populated."""
        policy = CIMDTrustPolicy()
        assert policy.trusted_domains == DEFAULT_TRUSTED_CIMD_DOMAINS
        assert "claude.ai" in policy.trusted_domains

    def test_is_trusted_exact_match(self):
        """Test is_trusted with exact domain match."""
        policy = CIMDTrustPolicy(trusted_domains=["example.com"])
        assert policy.is_trusted("example.com")
        assert policy.is_trusted("EXAMPLE.COM")  # Case insensitive
        assert not policy.is_trusted("other.com")

    def test_is_trusted_subdomain_match(self):
        """Test is_trusted with subdomain match."""
        policy = CIMDTrustPolicy(trusted_domains=["example.com"])
        assert policy.is_trusted("sub.example.com")
        assert policy.is_trusted("deep.sub.example.com")
        assert not policy.is_trusted("notexample.com")

    def test_is_blocked_exact_match(self):
        """Test is_blocked with exact domain match."""
        policy = CIMDTrustPolicy(blocked_domains=["evil.com"])
        assert policy.is_blocked("evil.com")
        assert policy.is_blocked("sub.evil.com")
        assert not policy.is_blocked("good.com")


class TestCIMDFetcher:
    """Tests for CIMDFetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create a CIMDFetcher for testing."""
        return CIMDFetcher()

    def test_is_cimd_client_id_valid_urls(self, fetcher: CIMDFetcher):
        """Test is_cimd_client_id accepts valid CIMD URLs."""
        assert fetcher.is_cimd_client_id("https://example.com/client.json")
        assert fetcher.is_cimd_client_id("https://example.com/path/to/client")
        assert fetcher.is_cimd_client_id("https://sub.example.com/cimd.json")

    def test_is_cimd_client_id_rejects_http(self, fetcher: CIMDFetcher):
        """Test is_cimd_client_id rejects HTTP URLs."""
        assert not fetcher.is_cimd_client_id("http://example.com/client.json")

    def test_is_cimd_client_id_rejects_root_path(self, fetcher: CIMDFetcher):
        """Test is_cimd_client_id rejects URLs with no path."""
        assert not fetcher.is_cimd_client_id("https://example.com/")
        assert not fetcher.is_cimd_client_id("https://example.com")

    def test_is_cimd_client_id_rejects_non_url(self, fetcher: CIMDFetcher):
        """Test is_cimd_client_id rejects non-URL strings."""
        assert not fetcher.is_cimd_client_id("client-123")
        assert not fetcher.is_cimd_client_id("my-client")
        assert not fetcher.is_cimd_client_id("")
        assert not fetcher.is_cimd_client_id("not a url")

    def test_validate_url_rejects_http(self, fetcher: CIMDFetcher):
        """Test that HTTP URLs are rejected."""
        with pytest.raises(CIMDValidationError) as exc_info:
            fetcher._validate_url("http://example.com/client.json")
        assert "HTTPS" in str(exc_info.value)

    def test_validate_url_rejects_root_path(self, fetcher: CIMDFetcher):
        """Test that URLs without path are rejected."""
        with pytest.raises(CIMDValidationError) as exc_info:
            fetcher._validate_url("https://example.com/")
        assert "non-root path" in str(exc_info.value)

    def test_validate_url_rejects_localhost(self, fetcher: CIMDFetcher):
        """Test that localhost URLs are rejected (SSRF protection)."""
        with pytest.raises(CIMDValidationError) as exc_info:
            fetcher._validate_url("https://localhost/client.json")
        assert "private" in str(exc_info.value).lower()

    def test_validate_url_rejects_private_ip(self, fetcher: CIMDFetcher):
        """Test that private IP URLs are rejected (SSRF protection)."""
        with pytest.raises(CIMDValidationError) as exc_info:
            fetcher._validate_url("https://192.168.1.1/client.json")
        assert "private" in str(exc_info.value).lower()

        with pytest.raises(CIMDValidationError) as exc_info:
            fetcher._validate_url("https://10.0.0.1/client.json")
        assert "private" in str(exc_info.value).lower()

    def test_validate_url_rejects_blocked_domain(self, fetcher: CIMDFetcher):
        """Test that blocked domains are rejected."""
        fetcher.trust_policy = CIMDTrustPolicy(blocked_domains=["evil.com"])
        with pytest.raises(CIMDValidationError) as exc_info:
            fetcher._validate_url("https://evil.com/client.json")
        assert "blocked" in str(exc_info.value).lower()

    def test_get_domain_extracts_hostname(self, fetcher: CIMDFetcher):
        """Test that get_domain extracts the hostname."""
        assert fetcher.get_domain("https://example.com/client.json") == "example.com"
        assert fetcher.get_domain("https://sub.example.com/path/client.json") == "sub.example.com"
        assert fetcher.get_domain("invalid") is None

    def test_validate_redirect_uri_exact_match(self, fetcher: CIMDFetcher):
        """Test redirect_uri validation with exact match."""
        doc = CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            redirect_uris=["http://localhost:3000/callback"],
        )
        assert fetcher.validate_redirect_uri(doc, "http://localhost:3000/callback")
        assert not fetcher.validate_redirect_uri(doc, "http://localhost:4000/callback")

    def test_validate_redirect_uri_wildcard_match(self, fetcher: CIMDFetcher):
        """Test redirect_uri validation with wildcard port."""
        doc = CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            redirect_uris=["http://localhost:*/callback"],
        )
        assert fetcher.validate_redirect_uri(doc, "http://localhost:3000/callback")
        assert fetcher.validate_redirect_uri(doc, "http://localhost:8080/callback")
        assert not fetcher.validate_redirect_uri(doc, "http://localhost:3000/other")

    def test_validate_redirect_uri_no_uris(self, fetcher: CIMDFetcher):
        """Test redirect_uri validation when no URIs specified."""
        doc = CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            redirect_uris=None,
        )
        assert not fetcher.validate_redirect_uri(doc, "http://localhost:3000/callback")


class TestCIMDFetcherHTTP:
    """Tests for CIMDFetcher HTTP fetching (using httpx mock)."""

    @pytest.fixture
    def fetcher(self):
        """Create a CIMDFetcher for testing."""
        return CIMDFetcher(cache_ttl=60)

    async def test_fetch_success(self, fetcher: CIMDFetcher, httpx_mock):
        """Test successful CIMD document fetch."""
        url = "https://example.com/client.json"
        doc_data = {
            "client_id": url,
            "client_name": "Test App",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        }
        httpx_mock.add_response(
            url=url,
            json=doc_data,
            headers={"content-type": "application/json"},
        )

        doc = await fetcher.fetch(url)
        assert str(doc.client_id) == url
        assert doc.client_name == "Test App"

    async def test_fetch_caches_result(self, fetcher: CIMDFetcher, httpx_mock):
        """Test that successful fetch is cached."""
        url = "https://example.com/client.json"
        doc_data = {
            "client_id": url,
            "client_name": "Test App",
        }
        httpx_mock.add_response(url=url, json=doc_data)

        # First fetch
        doc1 = await fetcher.fetch(url)

        # Second fetch should use cache (no HTTP request)
        doc2 = await fetcher.fetch(url)

        assert doc1.client_name == doc2.client_name
        # Should only have made one HTTP request
        assert len(httpx_mock.get_requests()) == 1

    async def test_fetch_client_id_mismatch(self, fetcher: CIMDFetcher, httpx_mock):
        """Test that client_id mismatch is rejected."""
        url = "https://example.com/client.json"
        doc_data = {
            "client_id": "https://other.com/client.json",  # Different URL
            "client_name": "Test App",
        }
        httpx_mock.add_response(url=url, json=doc_data)

        with pytest.raises(CIMDValidationError) as exc_info:
            await fetcher.fetch(url)
        assert "mismatch" in str(exc_info.value).lower()

    async def test_fetch_http_error(self, fetcher: CIMDFetcher, httpx_mock):
        """Test handling of HTTP errors."""
        url = "https://example.com/client.json"
        httpx_mock.add_response(url=url, status_code=404)

        with pytest.raises(CIMDFetchError) as exc_info:
            await fetcher.fetch(url)
        assert "404" in str(exc_info.value)

    async def test_fetch_invalid_json(self, fetcher: CIMDFetcher, httpx_mock):
        """Test handling of invalid JSON response."""
        url = "https://example.com/client.json"
        httpx_mock.add_response(url=url, content=b"not json")

        with pytest.raises(CIMDValidationError) as exc_info:
            await fetcher.fetch(url)
        assert "JSON" in str(exc_info.value)

    async def test_fetch_invalid_document(self, fetcher: CIMDFetcher, httpx_mock):
        """Test handling of invalid CIMD document."""
        url = "https://example.com/client.json"
        doc_data = {
            "client_id": url,
            "token_endpoint_auth_method": "client_secret_basic",  # Not allowed
        }
        httpx_mock.add_response(url=url, json=doc_data)

        with pytest.raises(CIMDValidationError) as exc_info:
            await fetcher.fetch(url)
        assert "Invalid CIMD document" in str(exc_info.value)

    async def test_cache_respects_max_age(self, fetcher: CIMDFetcher, httpx_mock):
        """Test that cache respects Cache-Control max-age."""
        url = "https://example.com/client.json"
        doc_data = {"client_id": url}
        httpx_mock.add_response(
            url=url,
            json=doc_data,
            headers={"cache-control": "max-age=3600"},
        )

        await fetcher.fetch(url)

        # Check that TTL was set correctly
        assert url in fetcher._cache
        _, expires_at = fetcher._cache[url]
        # Should be cached for at least 3600 seconds (minus some tolerance)
        import time
        assert expires_at > time.time() + 3500

    def test_clear_cache(self, fetcher: CIMDFetcher):
        """Test cache clearing."""
        # Manually add to cache
        from fastmcp.server.auth.cimd import CIMDDocument
        import time
        doc = CIMDDocument(client_id="https://example.com/client.json")  # type: ignore[arg-type]
        fetcher._cache["https://example.com/client.json"] = (doc, time.time() + 3600)

        # Clear specific URL
        fetcher.clear_cache("https://example.com/client.json")
        assert "https://example.com/client.json" not in fetcher._cache

        # Re-add and clear all
        fetcher._cache["url1"] = (doc, time.time() + 3600)
        fetcher._cache["url2"] = (doc, time.time() + 3600)
        fetcher.clear_cache()
        assert len(fetcher._cache) == 0
