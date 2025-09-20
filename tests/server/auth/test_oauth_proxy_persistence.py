"""Tests for OAuth proxy with persistent client storage."""

from pathlib import Path

import pytest
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from fastmcp.server.auth.oauth_proxy import OAuthProxy


class TestOAuthProxyPersistence:
    """Tests for OAuth proxy with persistent client storage."""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path: Path) -> Path:
        """Create a temporary cache directory."""
        cache_dir = tmp_path / "oauth-proxy-test"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @pytest.fixture
    def jwt_verifier(self):
        """Create a mock JWT verifier."""
        from unittest.mock import AsyncMock, Mock

        verifier = Mock()
        verifier.required_scopes = ["read", "write"]
        verifier.verify_token = AsyncMock(return_value=None)
        return verifier

    def create_oauth_proxy(
        self, jwt_verifier, client_cache_dir: Path | None = None
    ) -> OAuthProxy:
        """Create an OAuth proxy instance with specified cache directory."""
        return OAuthProxy(
            upstream_authorization_endpoint="https://github.com/login/oauth/authorize",
            upstream_token_endpoint="https://github.com/login/oauth/access_token",
            upstream_client_id="test-client-id",
            upstream_client_secret="test-client-secret",
            token_verifier=jwt_verifier,
            base_url="https://myserver.com",
            redirect_path="/auth/callback",
            client_cache_dir=client_cache_dir,
        )

    async def test_client_persists_across_proxy_instances(
        self, jwt_verifier, temp_cache_dir: Path
    ):
        """Test that registered clients persist across OAuth proxy instances."""
        # Create first proxy instance
        proxy1 = self.create_oauth_proxy(jwt_verifier, temp_cache_dir)

        # Register a client
        client_info = OAuthClientInformationFull(
            client_id="persistent-oauth-client",
            client_secret="oauth-secret-123",
            redirect_uris=[AnyUrl("http://localhost:54321/callback")],
            grant_types=["authorization_code", "refresh_token"],
            scope="read write",
        )
        await proxy1.register_client(client_info)

        # Verify it's registered
        client = await proxy1.get_client("persistent-oauth-client")
        assert client is not None
        assert client.client_id == "persistent-oauth-client"

        # Create new proxy instance (simulating server restart)
        proxy2 = self.create_oauth_proxy(jwt_verifier, temp_cache_dir)

        # Get the client from the new proxy instance (should load from storage)
        loaded_client = await proxy2.get_client("persistent-oauth-client")

        # Verify it persisted
        assert loaded_client is not None
        assert loaded_client.client_id == "persistent-oauth-client"
        assert loaded_client.client_secret == "oauth-secret-123"
        assert loaded_client.scope == "read write"
        assert len(loaded_client.redirect_uris) == 1
        assert str(loaded_client.redirect_uris[0]) == "http://localhost:54321/callback"

    async def test_multiple_clients_persistence(
        self, jwt_verifier, temp_cache_dir: Path
    ):
        """Test that multiple clients persist correctly."""
        # Create proxy and register multiple clients
        proxy1 = self.create_oauth_proxy(jwt_verifier, temp_cache_dir)

        clients = []
        for i in range(3):
            client = OAuthClientInformationFull(
                client_id=f"client-{i}",
                client_secret=f"secret-{i}",
                redirect_uris=[AnyUrl(f"http://localhost:{8080 + i}/callback")],
                scope=f"scope{i}",
            )
            clients.append(client)
            await proxy1.register_client(client)

        # Create new proxy instance
        proxy2 = self.create_oauth_proxy(jwt_verifier, temp_cache_dir)

        # Verify all clients persisted
        for i in range(3):
            loaded = await proxy2.get_client(f"client-{i}")
            assert loaded is not None
            assert loaded.client_secret == f"secret-{i}"
            assert loaded.scope == f"scope{i}"

    async def test_proxy_without_cache_dir_uses_default(self, jwt_verifier):
        """Test that proxy without specified cache_dir uses default location."""
        # Create proxy without specifying cache_dir
        proxy = self.create_oauth_proxy(jwt_verifier, client_cache_dir=None)

        # Register a client
        client_info = OAuthClientInformationFull(
            client_id="default-location-client",
            client_secret="default-secret",
            redirect_uris=[AnyUrl("http://localhost:9999/callback")],
        )
        await proxy.register_client(client_info)

        # Verify it's stored (this will use ~/.fastmcp/oauth-proxy-clients/)
        client = await proxy.get_client("default-location-client")
        assert client is not None

        # Clean up the default location to not leave test artifacts
        from fastmcp.server.auth.client_storage import OAuthClientStorage

        storage = OAuthClientStorage(cache_dir=None)
        await storage.delete_client("default-location-client")

    async def test_in_memory_cache_performance(
        self, jwt_verifier, temp_cache_dir: Path
    ):
        """Test that in-memory caching works for performance."""
        proxy = self.create_oauth_proxy(jwt_verifier, temp_cache_dir)

        # Register a client
        client_info = OAuthClientInformationFull(
            client_id="cached-client",
            client_secret="cached-secret",
            redirect_uris=[AnyUrl("http://localhost:7777/callback")],
        )
        await proxy.register_client(client_info)

        # First get - loads from storage to memory
        client1 = await proxy.get_client("cached-client")
        assert client1 is not None

        # Delete the file to simulate it being unavailable
        storage_file = temp_cache_dir / "client_cached-client.json"
        if storage_file.exists():
            storage_file.unlink()

        # Second get should still work from in-memory cache
        client2 = await proxy.get_client("cached-client")
        assert client2 is not None
        assert client2.client_id == "cached-client"

        # Create new proxy instance - now it won't find the client
        proxy2 = self.create_oauth_proxy(jwt_verifier, temp_cache_dir)
        client3 = await proxy2.get_client("cached-client")
        assert client3 is None  # Not in memory or storage
