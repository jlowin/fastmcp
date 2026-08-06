"""Encryption of the task-context snapshot at rest.

The snapshot a task carries holds the submitting caller's access token and every
inbound HTTP header, and it lives in the Docket backend for the task's TTL. A
distributed backend therefore keeps bearer credentials in Redis, where a
``rediss://`` URL protects the wire but not the stored value.

Setting ``FASTMCP_ENCRYPTION_KEY`` turns the stored snapshot into a Fernet token.
The same key must reach every server and worker on the queue, because the process
that restores a snapshot is rarely the one that captured it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import ClassVar

import fastmcp
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

# Domain separation: FASTMCP_ENCRYPTION_KEY is meant to serve other at-rest uses
# over time, and each derives its own Fernet key from this shared material.
_SNAPSHOT_KEY_SALT = "fastmcp-task-snapshot-key"

# Below this, warn: the keyspace is small enough that the offline attacker this
# feature defends against can search it even through PBKDF2. Matches the OAuth
# proxy's threshold for its signing-key material.
_SHORT_KEY_WARNING_LENGTH = 12


class SnapshotDecryptionError(Exception):
    """A stored snapshot could not be decrypted with the configured key.

    Raised for a wrong key, a tampered value, or a plaintext value written
    before the key was configured. The restore path lets this escape so the task
    fails, rather than running the tool as an anonymous caller.
    """


class SnapshotCodec(ABC):
    """Transforms snapshot payloads on their way to and from the backend.

    ``protected`` tells the restore path which failure contract applies: a
    protected snapshot that cannot be restored fails the task, an unprotected
    one degrades to an anonymous run with a warning.
    """

    protected: ClassVar[bool]

    @abstractmethod
    def encode(self, payload: str) -> str:
        """Return the stored form of a serialized snapshot."""

    @abstractmethod
    def decode(self, stored: str | bytes) -> str:
        """Return the serialized snapshot a stored value holds."""


class PlaintextCodec(SnapshotCodec):
    """Stores snapshots as-is; the contract when no encryption key is set."""

    protected = False

    def encode(self, payload: str) -> str:
        return payload

    def decode(self, stored: str | bytes) -> str:
        return stored.decode() if isinstance(stored, bytes) else stored


class EncryptedCodec(SnapshotCodec):
    """Encrypts snapshot payloads with a key derived from material.

    The material is a string from the environment, and nothing about a string
    proves it is random, so it is always treated as low-entropy: the Fernet key
    comes from PBKDF2, never from HKDF. The stretch costs about a second, paid
    once per process (see ``_codec_for``).
    """

    protected = True

    def __init__(self, material: str) -> None:
        from cryptography.fernet import Fernet

        from fastmcp.server.auth.jwt_issuer import derive_jwt_key

        if not material:
            raise ValueError(
                "FASTMCP_ENCRYPTION_KEY must not be empty. Unset it to store "
                "task snapshots as plaintext, or set at least 32 random "
                "characters."
            )
        if len(material) < _SHORT_KEY_WARNING_LENGTH:
            logger.warning(
                "The configured encryption key is shorter than %d characters; "
                "use at least 32 random characters.",
                _SHORT_KEY_WARNING_LENGTH,
            )
        key = derive_jwt_key(low_entropy_material=material, salt=_SNAPSHOT_KEY_SALT)

        self._fernet = Fernet(key=key)

    def encode(self, payload: str) -> str:
        """Return the encrypted form of a serialized snapshot."""
        return self._fernet.encrypt(payload.encode()).decode()

    def decode(self, stored: str | bytes) -> str:
        """Return the serialized snapshot a stored value holds.

        Raises ``SnapshotDecryptionError`` if the value was not produced by this
        key, including when it is unencrypted.
        """
        from cryptography.fernet import InvalidToken

        raw = stored.encode() if isinstance(stored, str) else stored
        try:
            return self._fernet.decrypt(raw).decode()
        except InvalidToken as e:
            raise SnapshotDecryptionError(
                "The stored task snapshot could not be decrypted with the "
                "configured FASTMCP_ENCRYPTION_KEY."
            ) from e


_PLAINTEXT_CODEC = PlaintextCodec()


@lru_cache(maxsize=4)
def _codec_for(material: str) -> EncryptedCodec:
    """One codec per key, so the derivation cost is paid once per process.

    The PBKDF2 stretch takes about a second, and every task submission and
    every restore needs a codec.
    """
    return EncryptedCodec(material)


def snapshot_codec() -> SnapshotCodec:
    """The codec for the configured key; the plaintext codec when none is set."""
    key = fastmcp.settings.encryption_key
    if key is None:
        return _PLAINTEXT_CODEC
    return _codec_for(key.get_secret_value())


def clear_codec_cache() -> None:
    """Drop the cached codecs, so a changed key takes effect."""
    _codec_for.cache_clear()
