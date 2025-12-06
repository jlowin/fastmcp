"""Tests for CIMD document creation utility."""

import pytest

from fastmcp.client.auth import create_cimd_document


class TestCreateCimdDocument:
    def test_basic_creation(self):
        doc = create_cimd_document("https://example.com/oauth/client.json")

        assert doc["client_id"] == "https://example.com/oauth/client.json"
        assert doc["client_name"] == "FastMCP Client"
        assert doc["token_endpoint_auth_method"] == "none"
        assert doc["grant_types"] == ["authorization_code", "refresh_token"]
        assert doc["response_types"] == ["code"]
        assert "redirect_uris" in doc
        assert len(doc["redirect_uris"]) > 0

    def test_custom_client_name(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            client_name="My Custom Client",
        )

        assert doc["client_name"] == "My Custom Client"

    def test_custom_redirect_uris(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            redirect_uris=["http://localhost:3000/callback"],
        )

        assert doc["redirect_uris"] == ["http://localhost:3000/callback"]

    def test_scopes(self):
        doc = create_cimd_document(
            "https://example.com/oauth/client.json",
            scopes=["openid", "profile", "email"],
        )

        assert doc["scope"] == "openid profile email"

    def test_no_scopes_excludes_field(self):
        doc = create_cimd_document("https://example.com/oauth/client.json")

        assert "scope" not in doc

    def test_rejects_http_url(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            create_cimd_document("http://example.com/oauth/client.json")

    def test_rejects_root_path(self):
        with pytest.raises(ValueError, match="non-root path"):
            create_cimd_document("https://example.com/")

    def test_rejects_no_path(self):
        with pytest.raises(ValueError, match="non-root path"):
            create_cimd_document("https://example.com")

    def test_well_known_path(self):
        doc = create_cimd_document("https://example.com/.well-known/oauth-client.json")

        assert doc["client_id"] == "https://example.com/.well-known/oauth-client.json"

    def test_excludes_none_values(self):
        doc = create_cimd_document("https://example.com/oauth/client.json")

        # These fields should not be present when None
        assert "client_secret" not in doc
        assert "client_id_issued_at" not in doc
        assert "client_secret_expires_at" not in doc
        assert "client_uri" not in doc
        assert "logo_uri" not in doc
