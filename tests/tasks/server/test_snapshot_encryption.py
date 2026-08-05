"""Tests for encryption of the task-context snapshot at rest (#4747).

The snapshot carries the submitting caller's access token and every inbound HTTP
header, and it is written to the Docket backend for the task's TTL. With a
distributed backend those credentials sit in Redis where the backend's operators
can read them. Setting ``FASTMCP_ENCRYPTION_KEY`` makes the snapshot a Fernet
token instead, and makes a worker that cannot decrypt one fail the task rather
than run it as an anonymous caller.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from fastmcp_tasks.context import TaskContextSnapshot
from fastmcp_tasks.encryption import (
    SnapshotCodec,
    SnapshotDecryptionError,
    clear_codec_cache,
    snapshot_codec,
)
from fastmcp_tasks.keys import task_redis_prefix
from pydantic import SecretStr

import fastmcp
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp_tasks import TasksExtension
from tests.tasks.task_helpers import (
    get_task,
    make_access_token,
    running_task_server,
    submit_task,
    wait_for_task,
)

KEY = "a-test-encryption-key-for-snapshots"
OTHER_KEY = "a-different-test-encryption-key-entirely"


@pytest.fixture
def encryption_key() -> Iterator[str]:
    """Configure the global encryption key for the duration of a test."""
    clear_codec_cache()
    previous = fastmcp.settings.encryption_key
    fastmcp.settings.encryption_key = SecretStr(KEY)
    try:
        yield KEY
    finally:
        fastmcp.settings.encryption_key = previous
        clear_codec_cache()


@pytest.fixture
def no_encryption_key() -> Iterator[None]:
    """Guarantee no key is configured, whatever the ambient environment holds."""
    clear_codec_cache()
    previous = fastmcp.settings.encryption_key
    fastmcp.settings.encryption_key = None
    try:
        yield
    finally:
        fastmcp.settings.encryption_key = previous
        clear_codec_cache()


@pytest.fixture
def sensitive_snapshot() -> TaskContextSnapshot:
    """A snapshot carrying a bearer token and an Authorization header."""
    token = make_access_token("client-a", "user-1")
    return TaskContextSnapshot(
        access_token_json=token.model_dump_json(),
        http_headers={"authorization": f"Bearer {token.token}", "x-trace-id": "abc"},
        origin_request_id="req-1",
        session_id="session-1",
        owning_tool_name="peek",
        owning_tool_version="1.0",
    )


class TestSnapshotCodec:
    def test_round_trips_a_payload(self):
        codec = SnapshotCodec(KEY)
        assert codec.decode(codec.encode('{"a": 1}')) == '{"a": 1}'

    def test_encoded_payload_hides_the_credentials(
        self, sensitive_snapshot: TaskContextSnapshot
    ):
        encoded = SnapshotCodec(KEY).encode(sensitive_snapshot.to_json())
        assert "token-client-a-user-1" not in encoded
        assert "authorization" not in encoded

    def test_decode_rejects_another_keys_payload(self):
        encoded = SnapshotCodec(OTHER_KEY).encode('{"a": 1}')
        with pytest.raises(SnapshotDecryptionError):
            SnapshotCodec(KEY).decode(encoded)

    def test_decode_rejects_plaintext(self):
        """A snapshot written before the key was set must not be trusted."""
        with pytest.raises(SnapshotDecryptionError):
            SnapshotCodec(KEY).decode('{"access_token_json": null}')

    def test_decode_accepts_bytes(self):
        """Redis hands back bytes on some backends."""
        codec = SnapshotCodec(KEY)
        assert codec.decode(codec.encode('{"a": 1}').encode()) == '{"a": 1}'

    def test_same_key_reuses_one_codec(self, encryption_key: str):
        assert snapshot_codec() is snapshot_codec()

    def test_no_codec_without_a_key(self, no_encryption_key: None):
        assert snapshot_codec() is None


class TestSnapshotSerialization:
    def test_json_round_trip_preserves_every_field(
        self, sensitive_snapshot: TaskContextSnapshot
    ):
        assert (
            TaskContextSnapshot.from_json(sensitive_snapshot.to_json())
            == sensitive_snapshot
        )


async def _read_stored_snapshot(mcp: FastMCP, task_scope: str, task_id: str) -> str:
    """Return the raw stored value of a task's snapshot key."""
    docket = mcp._docket
    assert docket is not None
    key = docket.key(f"{task_redis_prefix(task_scope)}:{task_id}:snapshot")
    async with docket.redis() as redis:
        raw = await redis.get(key)
    assert raw is not None
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def _write_stored_snapshot(
    mcp: FastMCP, task_scope: str, task_id: str, payload: str
) -> None:
    """Overwrite a task's stored snapshot value."""
    docket = mcp._docket
    assert docket is not None
    key = docket.key(f"{task_redis_prefix(task_scope)}:{task_id}:snapshot")
    async with docket.redis() as redis:
        await redis.set(key, payload)


@pytest.fixture
def echo_token_server() -> FastMCP:
    """A task server whose one tool reports the caller it restored."""
    mcp = FastMCP("snapshot-encryption-test")
    mcp.add_extension(TasksExtension())

    @mcp.tool(task=True)
    async def whoami() -> str:
        token = get_access_token()
        return token.token if token else "no-token"

    return mcp


class TestEncryptedSnapshotRoundTrip:
    async def test_worker_still_sees_the_submitting_caller(
        self, echo_token_server: FastMCP, encryption_key: str
    ):
        token = make_access_token("client-a", "user-1")

        async with running_task_server(echo_token_server):
            created = await submit_task(
                echo_token_server, "whoami", {}, access_token=token
            )
            final = await wait_for_task(
                echo_token_server, created.task_id, access_token=token
            )

        assert final.status == "completed"
        assert final.result is not None
        assert final.result["structuredContent"] == {"result": token.token}

    async def test_stored_value_is_not_readable(
        self, echo_token_server: FastMCP, encryption_key: str
    ):
        token = make_access_token("client-a", "user-1")

        async with running_task_server(echo_token_server):
            created = await submit_task(
                echo_token_server, "whoami", {}, access_token=token
            )
            stored = await _read_stored_snapshot(
                echo_token_server, "client-a|user-1", created.task_id
            )
            await wait_for_task(echo_token_server, created.task_id, access_token=token)

        assert token.token not in stored
        assert "authorization" not in stored
        with pytest.raises(json.JSONDecodeError):
            json.loads(stored)

    async def test_undecryptable_snapshot_fails_the_task(
        self,
        echo_token_server: FastMCP,
        encryption_key: str,
        caplog: pytest.LogCaptureFixture,
    ):
        """Fail closed: a worker that cannot recover the caller must not run.

        Running anyway would execute the tool as an anonymous caller, which for
        an authorization-sensitive tool is worse than not running at all. Docket
        surfaces this on the wire as a generic dependency failure, so the named
        cause has to come from the log.
        """
        token = make_access_token("client-a", "user-1")
        tampered = SnapshotCodec(OTHER_KEY).encode(TaskContextSnapshot().to_json())

        with caplog.at_level(logging.ERROR, logger="fastmcp_tasks.context"):
            async with running_task_server(echo_token_server):
                created = await submit_task(
                    echo_token_server, "whoami", {}, access_token=token
                )
                await _write_stored_snapshot(
                    echo_token_server, "client-a|user-1", created.task_id, tampered
                )
                final = await wait_for_task(
                    echo_token_server,
                    created.task_id,
                    access_token=token,
                    target_states=frozenset({"failed"}),
                )

        assert final.status == "failed"
        assert final.error is not None
        assert "FASTMCP_ENCRYPTION_KEY" in caplog.text


class TestUnencryptedByDefault:
    async def test_snapshot_stays_plaintext_without_a_key(
        self, echo_token_server: FastMCP, no_encryption_key: None
    ):
        """No key configured is the pre-existing contract, unchanged."""
        token = make_access_token("client-a", "user-1")

        async with running_task_server(echo_token_server):
            created = await submit_task(
                echo_token_server, "whoami", {}, access_token=token
            )
            stored = await _read_stored_snapshot(
                echo_token_server, "client-a|user-1", created.task_id
            )
            final = await wait_for_task(
                echo_token_server, created.task_id, access_token=token
            )

        assert json.loads(stored)["access_token_json"] is not None
        assert final.status == "completed"

    async def test_unreadable_snapshot_is_nonfatal_without_a_key(
        self, echo_token_server: FastMCP, no_encryption_key: None
    ):
        """Without encryption a corrupt snapshot still only degrades the caller."""
        token = make_access_token("client-a", "user-1")

        async with running_task_server(echo_token_server):
            created = await submit_task(
                echo_token_server, "whoami", {}, access_token=token
            )
            await _write_stored_snapshot(
                echo_token_server, "client-a|user-1", created.task_id, "not json"
            )
            final = await wait_for_task(
                echo_token_server, created.task_id, access_token=token
            )

        assert final.status == "completed"
        assert final.result is not None
        assert final.result["structuredContent"] == {"result": "no-token"}


class TestTaskStillResolvesAfterFailure:
    async def test_failed_task_reports_an_error(
        self, echo_token_server: FastMCP, encryption_key: str
    ):
        """A fail-closed task is still a well-formed `tasks/get` result."""
        token = make_access_token("client-a", "user-1")
        tampered = SnapshotCodec(OTHER_KEY).encode(TaskContextSnapshot().to_json())

        async with running_task_server(echo_token_server):
            created = await submit_task(
                echo_token_server, "whoami", {}, access_token=token
            )
            await _write_stored_snapshot(
                echo_token_server, "client-a|user-1", created.task_id, tampered
            )
            await wait_for_task(
                echo_token_server,
                created.task_id,
                access_token=token,
                target_states=frozenset({"failed"}),
            )
            fetched = await get_task(
                echo_token_server, created.task_id, access_token=token
            )

        assert fetched.status == "failed"
