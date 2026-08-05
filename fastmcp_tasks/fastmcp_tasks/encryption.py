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

from functools import lru_cache

import fastmcp
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

# Domain separation: FASTMCP_ENCRYPTION_KEY is meant to serve other at-rest uses
# over time, and each derives its own Fernet key from this shared material.
_SNAPSHOT_KEY_SALT = "fastmcp-task-snapshot-key"

# Below this, the material is too weak to feed HKDF, which assumes its input is
# already high-entropy. Matches the OAuth proxy's threshold for the same reason.
_MINIMUM_HIGH_ENTROPY_LENGTH = 12


class SnapshotDecryptionError(Exception):
    """A stored snapshot could not be decrypted with the configured key.

    Raised for a wrong key, a tampered value, or a plaintext value written
    before the key was configured. The restore path lets this escape so the task
    fails, rather than running the tool as an anonymous caller.
    """


class SnapshotCodec:
    """Encrypts and decrypts snapshot payloads with a key derived from material.

    Any string works as ``material``. High-entropy material is stretched with
    HKDF; a short passphrase goes through PBKDF2 instead, which is slower but
    survives the weaker input.
    """

    def __init__(self, material: str) -> None:
        from cryptography.fernet import Fernet

        from fastmcp.server.auth.jwt_issuer import derive_jwt_key

        if len(material) >= _MINIMUM_HIGH_ENTROPY_LENGTH:
            key = derive_jwt_key(
                high_entropy_material=material, salt=_SNAPSHOT_KEY_SALT
            )
        else:
            logger.warning(
                "The configured encryption key is shorter than %d characters; "
                "use at least 32 random characters.",
                _MINIMUM_HIGH_ENTROPY_LENGTH,
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


@lru_cache(maxsize=4)
def _codec_for(material: str) -> SnapshotCodec:
    """One codec per key, so the derivation cost is paid once per process.

    PBKDF2 over a short passphrase takes about a second, and every task
    submission and every restore needs a codec.
    """
    return SnapshotCodec(material)


def snapshot_codec() -> SnapshotCodec | None:
    """The codec for the configured key, or ``None`` when none is configured."""
    key = fastmcp.settings.encryption_key
    if key is None:
        return None
    return _codec_for(key.get_secret_value())


def clear_codec_cache() -> None:
    """Drop the cached codecs, so a changed key takes effect."""
    _codec_for.cache_clear()
