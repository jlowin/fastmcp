"""Tests for OAuth client persistent storage functionality."""

from pathlib import Path

import pytest
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from fastmcp.server.auth.client_storage import OAuthClientStorage
from fastmcp.server.auth.oauth_proxy import ProxyDCRClient


class TestOAuthClientStorage:
    """Tests for OAuth client persistent storage."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path: Path) -> Path:
        """Create a temporary cache directory."""
        cache_dir = tmp_path / "oauth-clients"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @pytest.fixture
    def client_storage(self, temp_cache_dir: Path) -> OAuthClientStorage:
        """Create a client storage instance with temp directory."""
        return OAuthClientStorage(cache_dir=temp_cache_dir)

    async def test_save_and_load_client(self, client_storage: OAuthClientStorage):
        """Test saving and loading a basic OAuth client."""
        # Create a client
        client = OAuthClientInformationFull(
            client_id="test-client-123",
            client_secret="test-secret",
            redirect_uris=[AnyUrl("http://localhost:8080/callback")],
            grant_types=["authorization_code", "refresh_token"],
            scope="read write",
        )

        # Save the client
        await client_storage.save_client(client)

        # Load the client back
        loaded_client = await client_storage.get_client("test-client-123")

        # Verify it matches
        assert loaded_client is not None
        assert loaded_client.client_id == "test-client-123"
        assert loaded_client.client_secret == "test-secret"
        assert len(loaded_client.redirect_uris) == 1
        assert str(loaded_client.redirect_uris[0]) == "http://localhost:8080/callback"
        assert loaded_client.grant_types == ["authorization_code", "refresh_token"]
        assert loaded_client.scope == "read write"

    async def test_save_and_load_proxy_dcr_client(
        self, client_storage: OAuthClientStorage
    ):
        """Test saving and loading a ProxyDCRClient with special handling."""
        # Create a ProxyDCRClient
        proxy_client = ProxyDCRClient(
            client_id="proxy-client-456",
            client_secret="proxy-secret",
            redirect_uris=[AnyUrl("http://localhost:9090/callback")],
            grant_types=["authorization_code"],
            scope="openid profile",
            token_endpoint_auth_method="none",
            allowed_redirect_uri_patterns=["http://localhost:*"],
        )

        # Save as ProxyDCRClient
        await client_storage.save_client(proxy_client, is_proxy_dcr=True)

        # Load it back with patterns
        loaded_client = await client_storage.get_client(
            "proxy-client-456", allowed_redirect_uri_patterns=["http://localhost:*"]
        )

        # Verify it's loaded as ProxyDCRClient
        assert loaded_client is not None
        assert isinstance(loaded_client, ProxyDCRClient)
        assert loaded_client.client_id == "proxy-client-456"
        assert loaded_client.client_secret == "proxy-secret"
        assert loaded_client.scope == "openid profile"

        # Test that the ProxyDCRClient validation works
        # This should pass for ProxyDCRClient but would fail for regular client
        validated_uri = loaded_client.validate_redirect_uri(
            AnyUrl("http://localhost:12345/different")
        )
        assert validated_uri is not None

    async def test_load_nonexistent_client(self, client_storage: OAuthClientStorage):
        """Test loading a client that doesn't exist returns None."""
        loaded_client = await client_storage.get_client("nonexistent-client")
        assert loaded_client is None

    async def test_delete_client(self, client_storage: OAuthClientStorage):
        """Test deleting a client from storage."""
        # Create and save a client
        client = OAuthClientInformationFull(
            client_id="delete-me",
            client_secret="secret",
            redirect_uris=[AnyUrl("http://localhost:8080/callback")],
        )
        await client_storage.save_client(client)

        # Verify it exists
        loaded = await client_storage.get_client("delete-me")
        assert loaded is not None

        # Delete it
        await client_storage.delete_client("delete-me")

        # Verify it's gone
        loaded = await client_storage.get_client("delete-me")
        assert loaded is None

    async def test_clear_all_clients(self, client_storage: OAuthClientStorage):
        """Test clearing all clients from storage."""
        # Create and save multiple clients
        for i in range(3):
            client = OAuthClientInformationFull(
                client_id=f"client-{i}",
                client_secret=f"secret-{i}",
                redirect_uris=[AnyUrl(f"http://localhost:{8080 + i}/callback")],
            )
            await client_storage.save_client(client)

        # Verify they exist
        for i in range(3):
            loaded = await client_storage.get_client(f"client-{i}")
            assert loaded is not None

        # Clear all
        await client_storage.clear_all()

        # Verify they're all gone
        for i in range(3):
            loaded = await client_storage.get_client(f"client-{i}")
            assert loaded is None

    async def test_client_persistence_across_instances(self, temp_cache_dir: Path):
        """Test that clients persist across storage instances (simulating restart)."""
        # Create first storage instance and save a client
        storage1 = OAuthClientStorage(cache_dir=temp_cache_dir)
        client = OAuthClientInformationFull(
            client_id="persistent-client",
            client_secret="persistent-secret",
            redirect_uris=[AnyUrl("http://localhost:8080/callback")],
            scope="read write delete",
        )
        await storage1.save_client(client)

        # Create new storage instance (simulating server restart)
        storage2 = OAuthClientStorage(cache_dir=temp_cache_dir)

        # Load the client from the new instance
        loaded_client = await storage2.get_client("persistent-client")

        # Verify it persisted
        assert loaded_client is not None
        assert loaded_client.client_id == "persistent-client"
        assert loaded_client.client_secret == "persistent-secret"
        assert loaded_client.scope == "read write delete"

    async def test_special_characters_in_client_id(
        self, client_storage: OAuthClientStorage
    ):
        """Test that client IDs with special characters are handled correctly."""
        # Create client with special characters in ID
        client = OAuthClientInformationFull(
            client_id="client.with/special:chars*in?id",
            client_secret="secret",
            redirect_uris=[AnyUrl("http://localhost:8080/callback")],
        )

        # Save and load it
        await client_storage.save_client(client)
        loaded = await client_storage.get_client("client.with/special:chars*in?id")

        # Verify it works
        assert loaded is not None
        assert loaded.client_id == "client.with/special:chars*in?id"
