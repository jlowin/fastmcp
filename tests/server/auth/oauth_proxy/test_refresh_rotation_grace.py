"""Tests for client refresh-token rotation grace (issue #4901).

Rotating the client-facing refresh token must not orphan the session when two
/token requests race on the same refresh token (client retries, multiple
tabs, background + foreground refresh). The second request arriving inside the
rotation grace window replays the already-issued pair instead of failing with
invalid_grant.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from key_value.aio.stores.memory import MemoryStore
from mcp.server.auth.provider import TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from fastmcp.server.auth.auth import RefreshToken, TokenVerifier
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.oauth_proxy.models import (
    DEFAULT_ROTATION_GRACE_PERIOD_SECONDS,
    JTIMapping,
    RefreshTokenMetadata,
    UpstreamTokenSet,
    _hash_token,
)

SCOPES = ["read", "write"]


@pytest.fixture
def jwt_verifier():
    verifier = Mock(spec=TokenVerifier)
    verifier.required_scopes = SCOPES
    verifier.verify_token = AsyncMock(return_value=None)
    return verifier


def _make_proxy(jwt_verifier, **kwargs):
    return OAuthProxy(
        upstream_authorization_endpoint="https://idp.example.com/authorize",
        upstream_token_endpoint="https://idp.example.com/token",
        upstream_client_id="test-client",
        upstream_client_secret="test-secret",
        token_verifier=jwt_verifier,
        base_url="https://proxy.example.com",
        jwt_signing_key="test-secret-key",
        client_storage=MemoryStore(),
        **kwargs,
    )


async def _register_client(proxy, client_id="test-client"):
    client = OAuthClientInformationFull(
        client_id=client_id,
        client_secret="test-secret",
        redirect_uris=[AnyUrl("http://localhost:12345/callback")],
    )
    await proxy.register_client(client)
    return client


async def _seed_session(proxy, client_id="test-client"):
    """Seed an upstream session + FastMCP refresh JWT; return the JWT string."""
    now = time.time()
    upstream_token_id = f"upstream-{client_id}"
    await proxy._upstream_token_store.put(
        key=upstream_token_id,
        value=UpstreamTokenSet(
            upstream_token_id=upstream_token_id,
            access_token="upstream-access-old",
            refresh_token="upstream-refresh",
            refresh_token_expires_at=now + 86400,
            expires_at=now + 3600,
            token_type="Bearer",
            scope=" ".join(SCOPES),
            client_id=client_id,
            created_at=now,
            raw_token_data={},
        ),
        ttl=86400,
    )
    old_jti = f"old-refresh-jti-{client_id}"
    old_jwt = proxy.jwt_issuer.issue_refresh_token(
        client_id=client_id,
        scopes=SCOPES,
        jti=old_jti,
        expires_in=86400,
    )
    await proxy._jti_mapping_store.put(
        key=old_jti,
        value=JTIMapping(
            jti=old_jti,
            upstream_token_id=upstream_token_id,
            created_at=now,
        ),
        ttl=86400,
    )
    await proxy._refresh_token_store.put(
        key=_hash_token(old_jwt),
        value=RefreshTokenMetadata(
            client_id=client_id,
            scopes=SCOPES,
            expires_at=int(now) + 86400,
            created_at=now,
        ),
        ttl=86400,
    )
    return old_jwt


def _mock_upstream_refresh():
    """Patch helper: upstream refresh succeeds without rotating its token."""
    mock_client = Mock()
    mock_client.refresh_token = AsyncMock(
        return_value={
            "access_token": "upstream-access-new",
            "refresh_token": "upstream-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    mock_client.aclose = AsyncMock()
    return patch.object(
        OAuthProxy, "_create_upstream_oauth_client", return_value=mock_client
    ), mock_client


def _as_refresh_token(token_str, client_id="test-client"):
    return RefreshToken(
        token=token_str,
        client_id=client_id,
        scopes=SCOPES,
        expires_at=int(time.time()) + 86400,
    )


class TestRotationGracePeriod:
    def test_default_grace_period(self, jwt_verifier):
        proxy = _make_proxy(jwt_verifier)
        assert (
            proxy._rotation_grace_period_seconds
            == DEFAULT_ROTATION_GRACE_PERIOD_SECONDS
            == 45.0
        )

    async def test_sequential_replay_within_grace_returns_same_pair(self, jwt_verifier):
        """Second exchange with the rotated-out token replays the issued pair."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)
        old = _as_refresh_token(old_jwt)

        patcher, mock_client = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(client, old, SCOPES)
            assert first.refresh_token is not None
            assert first.refresh_token != old_jwt

            # The load path (run first by the /token handler) also accepts it.
            loaded = await proxy.load_refresh_token(client, old_jwt)
            assert loaded is not None
            assert loaded.token == old_jwt
            assert loaded.client_id == "test-client"

            second = await proxy.exchange_refresh_token(client, old, SCOPES)

        assert second.access_token == first.access_token
        assert second.refresh_token == first.refresh_token
        # No second upstream round-trip: the replay is served from storage.
        mock_client.refresh_token.assert_awaited_once()

    async def test_concurrent_refresh_converges_on_single_pair(self, jwt_verifier):
        """Two in-flight exchanges of the same token both succeed identically."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)

        patcher, mock_client = _mock_upstream_refresh()
        with patcher:
            first, second = await asyncio.gather(
                proxy.exchange_refresh_token(
                    client, _as_refresh_token(old_jwt), SCOPES
                ),
                proxy.exchange_refresh_token(
                    client, _as_refresh_token(old_jwt), SCOPES
                ),
            )

        assert first.refresh_token is not None
        assert second.access_token == first.access_token
        assert second.refresh_token == first.refresh_token
        mock_client.refresh_token.assert_awaited_once()

    async def test_new_token_refreshes_normally_after_rotation(self, jwt_verifier):
        """Rotation still advances: the replayed pair's refresh token rotates."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)

        patcher, mock_client = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(
                client, _as_refresh_token(old_jwt), SCOPES
            )
            assert first.refresh_token is not None
            third = await proxy.exchange_refresh_token(
                client, _as_refresh_token(first.refresh_token), SCOPES
            )

        assert third.refresh_token != first.refresh_token
        assert third.access_token != first.access_token
        assert mock_client.refresh_token.await_count == 2

    async def test_grace_expiry_rejects_old_token(self, jwt_verifier):
        """Reuse past the window fails closed with invalid_grant."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)

        patcher, _ = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(
                client, _as_refresh_token(old_jwt), SCOPES
            )
            assert first.refresh_token is not None

        # Age the grace record past the window.
        record = await proxy._refresh_grace_store.get(key=_hash_token(old_jwt))
        assert record is not None
        record.rotated_at -= proxy._rotation_grace_period_seconds + 10
        await proxy._refresh_grace_store.put(
            key=_hash_token(old_jwt), value=record, ttl=60
        )

        assert await proxy.load_refresh_token(client, old_jwt) is None
        patcher, _ = _mock_upstream_refresh()
        with pytest.raises(TokenError) as exc_info:
            with patcher:
                await proxy.exchange_refresh_token(
                    client, _as_refresh_token(old_jwt), SCOPES
                )
        assert exc_info.value.error == "invalid_grant"

    async def test_grace_disabled_rejects_rotated_token_immediately(self, jwt_verifier):
        """rotation_grace_period_seconds=0 preserves the old fail-fast behavior."""
        proxy = _make_proxy(jwt_verifier, rotation_grace_period_seconds=0)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)

        patcher, _ = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(
                client, _as_refresh_token(old_jwt), SCOPES
            )
            assert first.refresh_token is not None

        assert await proxy._refresh_grace_store.get(key=_hash_token(old_jwt)) is None
        assert await proxy.load_refresh_token(client, old_jwt) is None
        patcher, _ = _mock_upstream_refresh()
        with pytest.raises(TokenError) as exc_info:
            with patcher:
                await proxy.exchange_refresh_token(
                    client, _as_refresh_token(old_jwt), SCOPES
                )
        assert exc_info.value.error == "invalid_grant"

    async def test_grace_replay_rejects_foreign_client(self, jwt_verifier):
        """A grace record never crosses client boundaries."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        other = await _register_client(proxy, client_id="other-client")
        old_jwt = await _seed_session(proxy)

        patcher, _ = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(
                client, _as_refresh_token(old_jwt), SCOPES
            )
            assert first.refresh_token is not None

        assert await proxy.load_refresh_token(other, old_jwt) is None
        patcher, _ = _mock_upstream_refresh()
        with pytest.raises(TokenError) as exc_info:
            with patcher:
                await proxy.exchange_refresh_token(
                    other, _as_refresh_token(old_jwt, client_id="other-client"), SCOPES
                )
        assert exc_info.value.error == "invalid_grant"

    async def test_grace_replay_refused_after_replacement_revoked(self, jwt_verifier):
        """Revoking the replacement pair also closes the replay path."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)

        patcher, _ = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(
                client, _as_refresh_token(old_jwt), SCOPES
            )
            assert first.refresh_token is not None

        await proxy.revoke_token(_as_refresh_token(first.refresh_token))

        patcher, _ = _mock_upstream_refresh()
        with pytest.raises(TokenError) as exc_info:
            with patcher:
                await proxy.exchange_refresh_token(
                    client, _as_refresh_token(old_jwt), SCOPES
                )
        assert exc_info.value.error == "invalid_grant"

    async def test_revoking_old_token_closes_replay(self, jwt_verifier):
        """Revoking the pre-rotation token deletes its grace record too."""
        proxy = _make_proxy(jwt_verifier)
        proxy.set_mcp_path("/mcp")
        client = await _register_client(proxy)
        old_jwt = await _seed_session(proxy)

        patcher, _ = _mock_upstream_refresh()
        with patcher:
            first = await proxy.exchange_refresh_token(
                client, _as_refresh_token(old_jwt), SCOPES
            )
            assert first.refresh_token is not None

        await proxy.revoke_token(_as_refresh_token(old_jwt))

        assert await proxy._refresh_grace_store.get(key=_hash_token(old_jwt)) is None
        assert await proxy.load_refresh_token(client, old_jwt) is None
