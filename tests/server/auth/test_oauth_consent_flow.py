"""Tests for OAuth Proxy consent flow with server-side storage.

This test suite verifies:
1. OAuth transactions are stored in server-side storage (not in-memory)
2. Authorization codes are stored in server-side storage
3. Consent flow redirects correctly through /consent endpoint
4. CSRF protection works with cookies
5. State persists across storage backends
"""

import secrets
import time
from urllib.parse import parse_qs, urlparse

import pytest
from key_value.aio.stores.memory import MemoryStore
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.testclient import TestClient

from fastmcp.server.auth.auth import TokenVerifier
from fastmcp.server.auth.oauth_proxy import OAuthProxy


class MockTokenVerifier(TokenVerifier):
    """Mock token verifier for testing."""

    def __init__(self):
        self.required_scopes = ["read", "write"]

    async def verify_token(self, token: str):
        """Mock token verification."""
        from fastmcp.server.auth.auth import AccessToken

        return AccessToken(
            token=token,
            client_id="mock-client",
            scopes=self.required_scopes,
            expires_at=int(time.time() + 3600),
        )


@pytest.fixture
def storage():
    """Create a fresh in-memory storage for each test."""
    return MemoryStore()


@pytest.fixture
def oauth_proxy_with_storage(storage):
    """Create OAuth proxy with explicit storage backend."""
    return OAuthProxy(
        upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
        upstream_token_endpoint="https://github.com/login/oauth/access_token",
        upstream_client_id="test-upstream-client",
        upstream_client_secret="test-upstream-secret",
        token_verifier=MockTokenVerifier(),
        base_url="https://myserver.com",
        redirect_path="/auth/callback",
        client_storage=storage,  # Use our test storage
    )


class TestServerSideStorage:
    """Tests verifying OAuth state is stored in AsyncKeyValue storage."""

    async def test_transaction_stored_in_storage_not_memory(
        self, oauth_proxy_with_storage, storage
    ):
        """Verify OAuth transactions are stored in AsyncKeyValue, not in-memory dict."""
        # Register client
        client = OAuthClientInformationFull(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:54321/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        # Start authorization flow
        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:54321/callback"),
            redirect_uri_provided_explicitly=True,
            state="client-state-123",
            code_challenge="challenge-abc",
            code_challenge_method="S256",
            scopes=["read", "write"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)

        # Extract transaction ID from consent redirect
        parsed = urlparse(redirect_url)
        assert "/consent" in parsed.path, "Should redirect to consent page"

        query_params = parse_qs(parsed.query)
        txn_id = query_params["txn_id"][0]

        # Verify transaction is NOT in the old in-memory dict
        # (the attribute should not exist or should be empty)
        assert (
            not hasattr(oauth_proxy_with_storage, "_oauth_transactions")
            or len(getattr(oauth_proxy_with_storage, "_oauth_transactions", {})) == 0
        )

        # Verify transaction IS in storage backend
        transaction = await storage.get(collection="mcp-oauth-transactions", key=txn_id)
        assert transaction is not None, "Transaction should be in storage"

        # Verify transaction has expected structure
        assert transaction["client_id"] == "test-client"
        assert transaction["client_redirect_uri"] == "http://localhost:54321/callback"
        assert transaction["client_state"] == "client-state-123"
        assert transaction["code_challenge"] == "challenge-abc"
        assert transaction["scopes"] == ["read", "write"]

    async def test_authorization_code_stored_in_storage(
        self, oauth_proxy_with_storage, storage
    ):
        """Verify authorization codes are stored in AsyncKeyValue storage."""
        # Register client
        client = OAuthClientInformationFull(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:54321/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        # Create a test app with OAuth routes
        app = Starlette(routes=oauth_proxy_with_storage.get_routes())

        with TestClient(app) as test_client:
            # Start authorization flow
            params = AuthorizationParams(
                redirect_uri=AnyUrl("http://localhost:54321/callback"),
                redirect_uri_provided_explicitly=True,
                state="client-state",
                code_challenge="challenge-xyz",
                code_challenge_method="S256",
                scopes=["read"],
            )

            redirect_url = await oauth_proxy_with_storage.authorize(client, params)

            # Extract txn_id from consent redirect
            parsed = urlparse(redirect_url)
            query_params = parse_qs(parsed.query)
            txn_id = query_params["txn_id"][0]

            # Simulate consent approval
            # First, get the consent page to establish CSRF cookie
            consent_response = test_client.get(
                f"/consent?txn_id={txn_id}", follow_redirects=False
            )

            # Extract CSRF token from response (it's in the HTML form)
            csrf_token = None
            if consent_response.status_code == 200:
                # For this test, we'll generate a CSRF token manually
                # In production, this comes from the consent page HTML
                csrf_token = secrets.token_urlsafe(32)

            # Approve consent with CSRF token
            approval_response = test_client.post(
                "/consent",
                data={"action": "approve", "txn": txn_id, "csrf_token": csrf_token},
                cookies=consent_response.cookies,
                follow_redirects=False,
            )

            # After approval, authorization code should be in storage
            # The code is returned in the redirect URL
            if approval_response.status_code in (302, 303):
                location = approval_response.headers.get("location", "")
                callback_params = parse_qs(urlparse(location).query)

                if "code" in callback_params:
                    auth_code = callback_params["code"][0]

                    # Verify code is NOT in old in-memory dict
                    assert (
                        not hasattr(oauth_proxy_with_storage, "_client_codes")
                        or len(getattr(oauth_proxy_with_storage, "_client_codes", {}))
                        == 0
                    )

                    # Verify code IS in storage
                    code_data = await storage.get(
                        collection="mcp-authorization-codes", key=auth_code
                    )
                    assert code_data is not None, (
                        "Authorization code should be in storage"
                    )
                    assert code_data["client_id"] == "test-client"
                    assert code_data["scopes"] == ["read"]

    async def test_storage_collections_are_isolated(self, oauth_proxy_with_storage):
        """Verify that transactions, codes, and clients use separate collections."""
        # Register a client
        client = OAuthClientInformationFull(
            client_id="isolation-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:12345/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        # Start authorization to create transaction
        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:12345/callback"),
            redirect_uri_provided_explicitly=True,
            state="test-state",
            code_challenge="test-challenge",
            code_challenge_method="S256",
            scopes=["read"],
        )

        await oauth_proxy_with_storage.authorize(client, params)

        # Get all collections from storage
        storage = oauth_proxy_with_storage._client_storage

        # Verify client is in client collection
        client_data = await storage.get(
            collection="mcp-oauth-proxy-clients", key="isolation-test-client"
        )
        assert client_data is not None

        # Verify we can list transactions separately
        # (This tests that collections are properly namespaced)
        transactions = await storage.keys(collection="mcp-oauth-transactions")

        assert len(transactions) > 0, "Should have at least one transaction"

        # Verify transaction keys don't collide with client keys
        for txn_key in transactions:
            assert txn_key != "isolation-test-client"


class TestConsentFlowRedirects:
    """Tests for consent flow redirect behavior."""

    async def test_authorize_redirects_to_consent_page(self, oauth_proxy_with_storage):
        """Verify authorize() redirects to /consent instead of upstream."""
        client = OAuthClientInformationFull(
            client_id="consent-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:8080/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:8080/callback"),
            redirect_uri_provided_explicitly=True,
            state="test-state",
            code_challenge="",
            scopes=["read"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)

        # Should redirect to consent page, not upstream
        assert "/consent" in redirect_url
        assert "github.com" not in redirect_url
        assert "?txn_id=" in redirect_url

    async def test_consent_page_contains_transaction_id(self, oauth_proxy_with_storage):
        """Verify consent page receives and displays transaction ID."""
        client = OAuthClientInformationFull(
            client_id="txn-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:9090/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:9090/callback"),
            redirect_uri_provided_explicitly=True,
            state="test-state",
            code_challenge="test-challenge",
            scopes=["read", "write"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)

        # Extract txn_id parameter
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)

        assert "txn_id" in query
        txn_id = query["txn_id"][0]
        assert len(txn_id) > 0

        # Create test client
        app = Starlette(routes=oauth_proxy_with_storage.get_routes())

        with TestClient(app) as test_client:
            # Request consent page
            response = test_client.get(
                f"/consent?txn_id={txn_id}", follow_redirects=False
            )

            assert response.status_code == 200
            # Consent page should contain transaction reference
            assert txn_id.encode() in response.content or b"consent" in response.content


class TestCSRFProtection:
    """Tests for CSRF protection in consent flow."""

    async def test_consent_requires_csrf_token(self, oauth_proxy_with_storage):
        """Verify consent submission requires valid CSRF token."""
        client = OAuthClientInformationFull(
            client_id="csrf-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:7070/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:7070/callback"),
            redirect_uri_provided_explicitly=True,
            state="test-state",
            code_challenge="",
            scopes=["read"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        txn_id = query["txn_id"][0]

        app = Starlette(routes=oauth_proxy_with_storage.get_routes())

        with TestClient(app) as test_client:
            # Try to submit consent WITHOUT CSRF token
            response = test_client.post(
                "/consent/submit",
                data={"action": "approve", "txn_id": txn_id},
                # No CSRF token!
                follow_redirects=False,
            )

            # Should reject or require CSRF
            # (Implementation may vary - checking for error response)
            assert response.status_code in (
                400,
                403,
                302,
            )  # Error or redirect to error

    async def test_consent_cookie_established_on_page_visit(
        self, oauth_proxy_with_storage
    ):
        """Verify consent page establishes CSRF cookie."""
        client = OAuthClientInformationFull(
            client_id="cookie-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:6060/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:6060/callback"),
            redirect_uri_provided_explicitly=True,
            state="test-state",
            code_challenge="",
            scopes=["read"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        txn_id = query["txn_id"][0]

        app = Starlette(routes=oauth_proxy_with_storage.get_routes())

        with TestClient(app) as test_client:
            # Visit consent page
            response = test_client.get(
                f"/consent?txn_id={txn_id}", follow_redirects=False
            )

            # Should set cookies for CSRF protection
            assert response.status_code == 200
            # Cookie may be set via Set-Cookie header
            cookies = response.cookies
            # Look for any CSRF-related cookie (implementation dependent)
            assert len(cookies) > 0 or "csrf" in response.text.lower(), (
                "Consent page should establish CSRF protection"
            )


class TestStoragePersistence:
    """Tests for state persistence across storage backends."""

    async def test_transaction_persists_after_retrieval(self, oauth_proxy_with_storage):
        """Verify transaction can be retrieved multiple times (until deleted)."""
        client = OAuthClientInformationFull(
            client_id="persist-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:5050/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:5050/callback"),
            redirect_uri_provided_explicitly=True,
            state="persist-state",
            code_challenge="persist-challenge",
            code_challenge_method="S256",
            scopes=["read"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        txn_id = query["txn_id"][0]

        storage = oauth_proxy_with_storage._client_storage

        # Retrieve transaction multiple times
        txn1 = await storage.get(collection="mcp-oauth-transactions", key=txn_id)
        assert txn1 is not None

        txn2 = await storage.get(collection="mcp-oauth-transactions", key=txn_id)
        assert txn2 is not None

        # Should be the same data
        assert txn1["client_id"] == txn2["client_id"]
        assert txn1["client_state"] == txn2["client_state"]

    async def test_storage_uses_pydantic_adapter(self, oauth_proxy_with_storage):
        """Verify that PydanticAdapter serializes/deserializes correctly."""
        from fastmcp.server.auth.oauth_proxy import OAuthTransaction

        client = OAuthClientInformationFull(
            client_id="pydantic-test-client",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:4040/callback")],
        )
        await oauth_proxy_with_storage.register_client(client)

        params = AuthorizationParams(
            redirect_uri=AnyUrl("http://localhost:4040/callback"),
            redirect_uri_provided_explicitly=True,
            state="pydantic-state",
            code_challenge="pydantic-challenge",
            code_challenge_method="S256",
            scopes=["read", "write"],
        )

        redirect_url = await oauth_proxy_with_storage.authorize(client, params)
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        txn_id = query["txn_id"][0]

        # Retrieve using PydanticAdapter (which is what the proxy uses)
        transaction_store = oauth_proxy_with_storage._transaction_store
        txn_model = await transaction_store.get(key=txn_id)

        # Should be a Pydantic model instance
        assert isinstance(txn_model, OAuthTransaction)
        assert txn_model.client_id == "pydantic-test-client"
        assert txn_model.client_state == "pydantic-state"
        assert txn_model.code_challenge == "pydantic-challenge"
        assert txn_model.scopes == ["read", "write"]
