"""Tests for CIMD document creation utility."""

import pytest

from fastmcp.client.auth import create_cimd_document


class TestCreateCimdDocument:
    """Tests for create_cimd_document utility."""

    def test_basic_public_client(self):
        """Public client with minimal required fields."""
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
        )

        assert doc["client_id"] == "https://example.com/oauth/client.json"
        assert doc["client_name"] == "FastMCP Client"
        assert doc["redirect_uris"] == ["http://localhost:8080/callback"]
        assert doc["grant_types"] == ["authorization_code", "refresh_token"]
        assert doc["response_types"] == ["code"]
        assert doc["token_endpoint_auth_method"] == "none"

    def test_custom_client_name(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
            client_name="My Custom Client",
        )

        assert doc["client_name"] == "My Custom Client"

    def test_multiple_redirect_uris(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=[
                "http://localhost:3000/callback",
                "http://localhost:8080/callback",
            ],
        )

        assert doc["redirect_uris"] == [
            "http://localhost:3000/callback",
            "http://localhost:8080/callback",
        ]

    def test_scopes(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
            scopes=["openid", "profile", "email"],
        )

        assert doc["scope"] == "openid profile email"

    def test_no_scopes_excludes_field(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
        )

        assert "scope" not in doc


class TestConfidentialClients:
    """Tests for confidential client support with private_key_jwt."""

    def test_jwks_uri_sets_private_key_jwt(self):
        """Providing jwks_uri makes it a confidential client."""
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["https://example.com/callback"],
            jwks_uri="https://example.com/.well-known/jwks.json",
        )

        assert doc["token_endpoint_auth_method"] == "private_key_jwt"
        assert doc["jwks_uri"] == "https://example.com/.well-known/jwks.json"
        assert "jwks" not in doc

    def test_inline_jwks_sets_private_key_jwt(self):
        """Providing inline jwks makes it a confidential client."""
        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "test-key-1",
                    "n": "0vx7agoebGcQSuuPiLJXZptN9...",
                    "e": "AQAB",
                }
            ]
        }
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["https://example.com/callback"],
            jwks=jwks,
        )

        assert doc["token_endpoint_auth_method"] == "private_key_jwt"
        assert doc["jwks"] == jwks
        assert "jwks_uri" not in doc

    def test_cannot_provide_both_jwks_uri_and_jwks(self):
        """Cannot provide both jwks_uri and inline jwks."""
        with pytest.raises(ValueError, match="either jwks_uri or jwks"):
            create_cimd_document(
                "https://example.com/oauth/client.json",
                redirect_uris=["https://example.com/callback"],
                jwks_uri="https://example.com/.well-known/jwks.json",
                jwks={"keys": []},
            )


class TestOptionalMetadataFields:
    """Tests for optional metadata fields."""

    def test_client_uri(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
            client_uri="https://example.com",
        )

        assert doc["client_uri"] == "https://example.com"

    def test_logo_uri(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
            logo_uri="https://example.com/logo.png",
        )

        assert doc["logo_uri"] == "https://example.com/logo.png"

    def test_contacts(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:8080/callback"],
            contacts=["admin@example.com", "security@example.com"],
        )

        assert doc["contacts"] == ["admin@example.com", "security@example.com"]

    def test_invalid_client_uri_rejected(self):
        with pytest.raises(Exception):  # Pydantic validation error
            create_cimd_document(
                "https://example.com/oauth/client.json",
                redirect_uris=["http://localhost:8080/callback"],
                client_uri="not-a-valid-url",
            )

    def test_invalid_logo_uri_rejected(self):
        with pytest.raises(Exception):  # Pydantic validation error
            create_cimd_document(
                "https://example.com/oauth/client.json",
                redirect_uris=["http://localhost:8080/callback"],
                logo_uri="not-a-valid-url",
            )


class TestUrlValidation:
    """Tests for CIMD URL validation per IETF draft."""

    def test_rejects_http_url(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            create_cimd_document(
                "http://example.com/oauth/client.json",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_rejects_root_path(self):
        with pytest.raises(ValueError, match="non-root path"):
            create_cimd_document(
                "https://example.com/",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_rejects_no_path(self):
        with pytest.raises(ValueError, match="non-root path"):
            create_cimd_document(
                "https://example.com",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_rejects_fragment(self):
        with pytest.raises(ValueError, match="fragment"):
            create_cimd_document(
                "https://example.com/client.json#section",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_rejects_credentials(self):
        with pytest.raises(ValueError, match="credentials"):
            create_cimd_document(
                "https://user:pass@example.com/client.json",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_rejects_dot_segments(self):
        with pytest.raises(ValueError, match="dot segments"):
            create_cimd_document(
                "https://example.com/../client.json",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_rejects_single_dot_segment(self):
        with pytest.raises(ValueError, match="dot segments"):
            create_cimd_document(
                "https://example.com/./client.json",
                redirect_uris=["http://localhost:8080/callback"],
            )

    def test_well_known_path_allowed(self):
        doc = create_cimd_document(
            "https://example.com/.well-known/oauth-client.json",
            redirect_uris=["http://localhost:8080/callback"],
        )

        assert doc["client_id"] == "https://example.com/.well-known/oauth-client.json"

    def test_query_string_allowed(self):
        """Query strings are discouraged but permitted."""
        doc = create_cimd_document(
            "https://example.com/client.json?version=1",
            redirect_uris=["http://localhost:8080/callback"],
        )

        assert doc["client_id"] == "https://example.com/client.json?version=1"

    def test_port_allowed(self):
        doc = create_cimd_document(
            "https://example.com:8443/client.json",
            redirect_uris=["http://localhost:8080/callback"],
        )

        assert doc["client_id"] == "https://example.com:8443/client.json"
