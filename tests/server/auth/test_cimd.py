"""Unit tests for CIMD (Client ID Metadata Document) functionality."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fastmcp.server.auth.cimd import (
    DEFAULT_TRUSTED_CIMD_DOMAINS,
    CIMDDocument,
    CIMDFetcher,
    CIMDFetchError,
    CIMDTrustPolicy,
    CIMDValidationError,
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
        """Test that default trusted domains list is empty (opt-in only)."""
        policy = CIMDTrustPolicy()
        assert policy.trusted_domains == DEFAULT_TRUSTED_CIMD_DOMAINS
        assert policy.trusted_domains == []  # No defaults - server operators configure

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
        assert (
            fetcher.get_domain("https://sub.example.com/path/client.json")
            == "sub.example.com"
        )
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


class TestCIMDAssertionValidator:
    """Tests for CIMDAssertionValidator (private_key_jwt support)."""

    @pytest.fixture
    def validator(self):
        """Create a CIMDAssertionValidator for testing."""
        from fastmcp.server.auth.cimd import CIMDAssertionValidator

        return CIMDAssertionValidator()

    @pytest.fixture
    def key_pair(self):
        """Generate RSA key pair for testing."""
        from fastmcp.server.auth.providers.jwt import RSAKeyPair

        return RSAKeyPair.generate()

    @pytest.fixture
    def jwks(self, key_pair):
        """Create JWKS from key pair."""
        import base64

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        # Load public key
        public_key = serialization.load_pem_public_key(
            key_pair.public_key.encode(), backend=default_backend()
        )

        # Get RSA public numbers
        from cryptography.hazmat.primitives.asymmetric import rsa

        if isinstance(public_key, rsa.RSAPublicKey):
            numbers = public_key.public_numbers()

            # Convert to JWK format
            return {
                "keys": [
                    {
                        "kty": "RSA",
                        "kid": "test-key-1",
                        "use": "sig",
                        "alg": "RS256",
                        "n": base64.urlsafe_b64encode(
                            numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
                        )
                        .rstrip(b"=")
                        .decode(),
                        "e": base64.urlsafe_b64encode(
                            numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
                        )
                        .rstrip(b"=")
                        .decode(),
                    }
                ]
            }

    @pytest.fixture
    def cimd_doc_with_jwks_uri(self):
        """Create CIMD document with jwks_uri."""
        return CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            token_endpoint_auth_method="private_key_jwt",
            jwks_uri="https://example.com/.well-known/jwks.json",  # type: ignore[arg-type]
        )

    @pytest.fixture
    def cimd_doc_with_inline_jwks(self, jwks):
        """Create CIMD document with inline JWKS."""
        return CIMDDocument(
            client_id="https://example.com/client.json",  # type: ignore[arg-type]
            token_endpoint_auth_method="private_key_jwt",
            jwks=jwks,
        )

    async def test_valid_assertion_with_jwks_uri(
        self, validator, key_pair, cimd_doc_with_jwks_uri, httpx_mock
    ):
        """Test that valid JWT assertion passes validation (jwks_uri)."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Mock JWKS endpoint
        import base64

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        public_key = serialization.load_pem_public_key(
            key_pair.public_key.encode(), backend=default_backend()
        )
        from cryptography.hazmat.primitives.asymmetric import rsa

        assert isinstance(public_key, rsa.RSAPublicKey)
        numbers = public_key.public_numbers()

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "test-key-1",
                    "use": "sig",
                    "alg": "RS256",
                    "n": base64.urlsafe_b64encode(
                        numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
                    )
                    .rstrip(b"=")
                    .decode(),
                    "e": base64.urlsafe_b64encode(
                        numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
                    )
                    .rstrip(b"=")
                    .decode(),
                }
            ]
        }

        httpx_mock.add_response(
            url="https://example.com/.well-known/jwks.json", json=jwks
        )

        # Create valid assertion
        assertion = key_pair.create_token(
            subject=client_id,
            issuer=client_id,
            audience=token_endpoint,
            additional_claims={"jti": "unique-jti-123"},
            kid="test-key-1",
        )

        # Should validate successfully
        assert await validator.validate_assertion(
            assertion, client_id, token_endpoint, cimd_doc_with_jwks_uri
        )

    async def test_valid_assertion_with_inline_jwks(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that valid JWT assertion passes validation (inline JWKS)."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create valid assertion
        assertion = key_pair.create_token(
            subject=client_id,
            issuer=client_id,
            audience=token_endpoint,
            additional_claims={"jti": "unique-jti-456"},
            kid="test-key-1",
        )

        # Should validate successfully
        assert await validator.validate_assertion(
            assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
        )

    async def test_rejects_wrong_issuer(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that wrong issuer is rejected."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create assertion with wrong issuer
        assertion = key_pair.create_token(
            subject=client_id,
            issuer="https://attacker.com",  # Wrong!
            audience=token_endpoint,
            additional_claims={"jti": "unique-jti-789"},
            kid="test-key-1",
        )

        with pytest.raises(ValueError) as exc_info:
            await validator.validate_assertion(
                assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
            )
        assert "Invalid JWT assertion" in str(exc_info.value)

    async def test_rejects_wrong_audience(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that wrong audience is rejected."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create assertion with wrong audience
        assertion = key_pair.create_token(
            subject=client_id,
            issuer=client_id,
            audience="https://wrong-endpoint.com/token",  # Wrong!
            additional_claims={"jti": "unique-jti-abc"},
            kid="test-key-1",
        )

        with pytest.raises(ValueError) as exc_info:
            await validator.validate_assertion(
                assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
            )
        assert "Invalid JWT assertion" in str(exc_info.value)

    async def test_rejects_wrong_subject(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that wrong subject claim is rejected."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create assertion with wrong subject
        assertion = key_pair.create_token(
            subject="https://different-client.com",  # Wrong!
            issuer=client_id,
            audience=token_endpoint,
            additional_claims={"jti": "unique-jti-def"},
            kid="test-key-1",
        )

        with pytest.raises(ValueError) as exc_info:
            await validator.validate_assertion(
                assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
            )
        assert "sub claim must be" in str(exc_info.value)

    async def test_rejects_missing_jti(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that missing jti claim is rejected."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create assertion without jti
        assertion = key_pair.create_token(
            subject=client_id,
            issuer=client_id,
            audience=token_endpoint,
            # No jti!
            kid="test-key-1",
        )

        with pytest.raises(ValueError) as exc_info:
            await validator.validate_assertion(
                assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
            )
        assert "jti claim" in str(exc_info.value)

    async def test_rejects_replayed_jti(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that replayed JTI is detected and rejected."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create assertion
        assertion = key_pair.create_token(
            subject=client_id,
            issuer=client_id,
            audience=token_endpoint,
            additional_claims={"jti": "replayed-jti"},
            kid="test-key-1",
        )

        # First use should succeed
        assert await validator.validate_assertion(
            assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
        )

        # Second use with same jti should fail (replay attack)
        with pytest.raises(ValueError) as exc_info:
            await validator.validate_assertion(
                assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
            )
        assert "replay" in str(exc_info.value).lower()

    async def test_rejects_expired_token(
        self, validator, key_pair, cimd_doc_with_inline_jwks
    ):
        """Test that expired tokens are rejected."""
        client_id = "https://example.com/client.json"
        token_endpoint = "https://oauth.example.com/token"

        # Create expired assertion (expired 1 hour ago)
        assertion = key_pair.create_token(
            subject=client_id,
            issuer=client_id,
            audience=token_endpoint,
            additional_claims={"jti": "expired-jti"},
            expires_in_seconds=-3600,  # Negative = expired
            kid="test-key-1",
        )

        with pytest.raises(ValueError) as exc_info:
            await validator.validate_assertion(
                assertion, client_id, token_endpoint, cimd_doc_with_inline_jwks
            )
        assert "Invalid JWT assertion" in str(exc_info.value)


class TestCIMDClientManager:
    """Tests for CIMDClientManager."""

    @pytest.fixture
    def manager(self):
        """Create a CIMDClientManager for testing."""
        from fastmcp.server.auth.cimd import CIMDClientManager

        return CIMDClientManager(enable_cimd=True)

    @pytest.fixture
    def disabled_manager(self):
        """Create a disabled CIMDClientManager for testing."""
        from fastmcp.server.auth.cimd import CIMDClientManager

        return CIMDClientManager(enable_cimd=False)

    def test_is_cimd_client_id_enabled(self, manager):
        """Test CIMD URL detection when enabled."""
        assert manager.is_cimd_client_id("https://example.com/client.json")
        assert not manager.is_cimd_client_id("regular-client-id")

    def test_is_cimd_client_id_disabled(self, disabled_manager):
        """Test CIMD URL detection when disabled."""
        assert not disabled_manager.is_cimd_client_id("https://example.com/client.json")
        assert not disabled_manager.is_cimd_client_id("regular-client-id")

    async def test_get_client_success(self, manager, httpx_mock):
        """Test successful CIMD client creation."""
        url = "https://example.com/client.json"
        doc_data = {
            "client_id": url,
            "client_name": "Test App",
            "redirect_uris": ["http://localhost:3000/callback"],
            "token_endpoint_auth_method": "none",
        }
        httpx_mock.add_response(url=url, json=doc_data)

        client = await manager.get_client(url)
        assert client is not None
        assert client.client_id == url
        assert client.client_name == "Test App"
        assert client.allowed_redirect_uri_patterns == [
            "http://localhost:3000/callback"
        ]

    async def test_get_client_disabled(self, disabled_manager):
        """Test that get_client returns None when disabled."""
        client = await disabled_manager.get_client("https://example.com/client.json")
        assert client is None

    async def test_get_client_fetch_failure(self, manager, httpx_mock):
        """Test that get_client returns None on fetch failure."""
        url = "https://example.com/client.json"
        httpx_mock.add_response(url=url, status_code=404)

        client = await manager.get_client(url)
        assert client is None

    def test_should_skip_consent_for_trusted_domain(self, manager):
        """Test that trusted domains skip consent."""
        from fastmcp.server.auth.cimd import CIMDClientManager, CIMDTrustPolicy

        manager = CIMDClientManager(
            enable_cimd=True,
            trust_policy=CIMDTrustPolicy(trusted_domains=["example.com"]),
        )

        assert manager.should_skip_consent("https://example.com/client.json")
        assert manager.should_skip_consent("https://sub.example.com/client.json")
        assert not manager.should_skip_consent("https://other.com/client.json")

    def test_should_skip_consent_disabled(self, disabled_manager):
        """Test that consent skip returns False when disabled."""
        assert not disabled_manager.should_skip_consent(
            "https://example.com/client.json"
        )

    def test_get_domain(self, manager):
        """Test domain extraction from CIMD URL."""
        assert manager.get_domain("https://example.com/client.json") == "example.com"
        assert (
            manager.get_domain("https://sub.example.com/path/client.json")
            == "sub.example.com"
        )
        assert manager.get_domain("invalid-url") is None
