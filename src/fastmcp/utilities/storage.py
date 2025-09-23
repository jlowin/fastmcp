"""Key-value storage utilities for persistent data management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import pydantic_core
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis import Redis
from redis.retry import Retry

from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.types import NotSet, NotSetT

logger = get_logger(__name__)


class KVStorage(Protocol):
    """Protocol for key-value storage of JSON data."""

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get a JSON dict by key."""
        ...

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store a JSON dict by key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a value by key."""
        ...


class JSONFileStorage:
    """File-based key-value storage for JSON data with automatic metadata tracking.

    Each key-value pair is stored as a separate JSON file on disk.
    Keys are sanitized to be filesystem-safe.

    The storage automatically wraps all data with metadata:
    - timestamp: Timestamp when the entry was last written

    Args:
        cache_dir: Directory for storing JSON files
    """

    def __init__(self, cache_dir: Path):
        """Initialize JSON file storage."""
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True, parents=True)

    def _get_safe_key(self, key: str) -> str:
        """Convert key to filesystem-safe string."""
        safe_key = key

        # Replace problematic characters with underscores
        for char in [".", "/", "\\", ":", "*", "?", '"', "<", ">", "|", " "]:
            safe_key = safe_key.replace(char, "_")

        # Compress multiple underscores into one
        while "__" in safe_key:
            safe_key = safe_key.replace("__", "_")

        # Strip leading and trailing underscores
        safe_key = safe_key.strip("_")

        return safe_key

    def _get_file_path(self, key: str) -> Path:
        """Get the file path for a given key."""
        safe_key = self._get_safe_key(key)
        return self.cache_dir / f"{safe_key}.json"

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get a JSON dict from storage by key.

        Args:
            key: The key to retrieve

        Returns:
            The stored dict or None if not found
        """
        path = self._get_file_path(key)
        try:
            wrapper = json.loads(path.read_text())

            # Expect wrapped format with metadata
            if not isinstance(wrapper, dict) or "data" not in wrapper:
                logger.warning(f"Invalid storage format for key '{key}'")
                return None

            logger.debug(f"Loaded data for key '{key}'")
            return wrapper["data"]

        except FileNotFoundError:
            logger.debug(f"No data found for key '{key}'")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to load data for key '{key}': {e}")
            return None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store a JSON dict with metadata.

        Args:
            key: The key to store under
            value: The dict to store
        """
        import time

        path = self._get_file_path(key)
        current_time = time.time()

        # Create wrapper with metadata
        wrapper = {
            "data": value,
            "timestamp": current_time,
        }

        # Use pydantic_core for consistent JSON serialization
        json_data = pydantic_core.to_json(wrapper, fallback=str)
        path.write_bytes(json_data)
        logger.debug(f"Saved data for key '{key}'")

    async def delete(self, key: str) -> None:
        """Delete a value from storage.

        Args:
            key: The key to delete
        """
        path = self._get_file_path(key)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted data for key '{key}'")

    async def cleanup_old_entries(
        self,
        max_age_seconds: int = 30 * 24 * 60 * 60,  # 30 days default
    ) -> int:
        """Remove entries older than the specified age.

        Uses the timestamp field to determine age.

        Args:
            max_age_seconds: Maximum age in seconds (default 30 days)

        Returns:
            Number of entries removed
        """
        import time

        current_time = time.time()
        removed_count = 0

        for json_file in self.cache_dir.glob("*.json"):
            try:
                # Read the file and check timestamp
                wrapper = json.loads(json_file.read_text())

                # Check wrapped format
                if not isinstance(wrapper, dict) or "data" not in wrapper:
                    continue  # Invalid format, skip

                if "timestamp" not in wrapper:
                    continue  # No timestamp field, skip

                entry_age = current_time - wrapper["timestamp"]
                if entry_age > max_age_seconds:
                    json_file.unlink()
                    removed_count += 1
                    logger.debug(
                        f"Removed old entry '{json_file.stem}' (age: {entry_age:.0f}s)"
                    )

            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Error reading {json_file.name}: {e}")
                continue

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old entries from storage")

        return removed_count


class InMemoryStorage:
    """In-memory key-value storage for JSON data.

    Simple dict-based storage that doesn't persist across restarts.
    Useful for testing or environments where file storage isn't available.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get a JSON dict from memory by key."""
        return self._data.get(key)

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store a JSON dict in memory."""
        self._data[key] = value

    async def delete(self, key: str) -> None:
        """Delete a value from memory."""
        self._data.pop(key, None)


class RedisStorageSettings(BaseSettings):
    """Settings for Redis based storage."""

    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_SERVER_STORAGE_REDIS_",
        env_file=".env",
        extra="ignore",
    )

    host: str | None = None
    port: int | None = None
    db: int | None = None
    protocol: int | None = None
    ssl: bool | None = None
    ssl_cert_reqs: str | None = None
    max_connections: int | None = None
    health_check_interval: int | None = None
    expire_in_seconds: int | None = None


class RedisStorage:
    """Redis based key-value storage for serializable JSON data."""

    def __init__(
        self,
        *,
        host: str | NotSetT = NotSet,
        port: int | NotSetT = NotSet,
        db: int | NotSetT = NotSet,
        protocol: int | NotSetT = NotSet,
        ssl: bool | NotSetT = NotSet,
        ssl_cert_reqs: str | NotSetT = NotSet,
        max_connections: int | NotSetT = NotSet,
        health_check_interval: int | NotSetT = NotSet,
        expire_in_seconds: int | NotSetT = NotSet,
        retry: Retry | None = None,
        retry_on_error: list[type[Exception]] | None = None,
    ) -> None:
        """Initialize Redis storage.

        Args:
            host: The Redis host
            port: The Redis port (defaults to 6379)
            db: The Redis db index (defaults to 0)
            protocol: The Redis protocol version (defaults to 2)
            ssl: Enable SSL connections (defaults to False)
            ssl_cert_reqs: The SSL verify mode (defaults to "required")
            max_connections: The maximum nummber of connections to the Redis server (defaults to None)
            health_check_interval: The health check interval in seconds (defaults to 0)
            expire_in_seconds: The cache entry expiration in seconds (defaults to None)
            retry: The Redis retry object to manage retries (defaults to None)
            retry_on_error: A list of exception types which should trigger a retry (defaults to None)
        """
        settings = RedisStorageSettings.model_validate(
            {
                k: v
                for k, v in {
                    "host": host,
                    "port": port,
                    "db": db,
                    "protocol": protocol,
                    "ssl": ssl,
                    "ssl_cert_reqs": ssl_cert_reqs,
                    "max_connections": max_connections,
                    "health_check_interval": health_check_interval,
                    "expire_in_seconds": expire_in_seconds,
                }.items()
                if v is not NotSet
            }
        )

        if not settings.host:
            raise ValueError(
                "host is required - set via parameter or FASTMCP_SERVER_STORAGE_REDIS_HOST"
            )

        # Configuration based arguments
        redis_kwargs = {"host": settings.host}

        def set_kwargs(attrs: list[str]) -> None:
            for attr in attrs:
                if (value := getattr(settings, attr, None)) is not None:
                    redis_kwargs[attr] = value

        set_kwargs(
            [
                "port",
                "db",
                "protocol",
                "ssl",
                "ssl_cert_reqs",
                "max_connections",
                "health_check_interval",
            ]
        )

        # Code based arguments
        if retry:
            redis_kwargs["retry"] = retry

        if retry_on_error:
            redis_kwargs["retry_on_error"] = retry_on_error

        self.redis = Redis(**redis_kwargs)
        self.redis.ping()

        # Cache entry settings
        self.ex = settings.expire_in_seconds

        logger.info(f"Initialized Redis storage on host '{settings.host}")

    async def get(self, key: str) -> dict[str, Any] | None:
        """Get a JSON dict by key."""
        redis_value = self.redis.get(key)
        return json.loads(redis_value)

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store a JSON dict by key."""
        redis_value = json.dumps(value)
        self.redis.set(key, redis_value, ex=self.ex)

    async def delete(self, key: str) -> None:
        """Delete a value by key."""
        self.redis.delete(key)
