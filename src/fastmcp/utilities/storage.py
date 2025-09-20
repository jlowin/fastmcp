"""File-based storage utilities for persistent data management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class FileKVStorage(Protocol):
    """Protocol for file-based key-value storage."""

    async def get(self, key: str) -> Any | None:
        """Get a value by key."""
        ...

    async def set(self, key: str, value: Any) -> None:
        """Set a value by key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a value by key."""
        ...

    async def clear(self) -> None:
        """Clear all stored values."""
        ...


class JSONFileStorage:
    """JSON file-based key-value storage implementation.

    This class provides a simple file-based storage mechanism for JSON-serializable
    data. Each key-value pair is stored as a separate JSON file on disk.

    Args:
        cache_dir: Directory for storing JSON files
        prefix: Prefix for all file names (e.g. "oauth_client")
    """

    def __init__(self, cache_dir: Path, prefix: str = ""):
        """Initialize JSON file storage."""
        self.cache_dir = cache_dir
        self.prefix = prefix
        self.cache_dir.mkdir(exist_ok=True, parents=True)

    def _get_safe_key(self, key: str) -> str:
        """Convert key to filesystem-safe string."""
        # Replace problematic characters with underscores
        safe_key = key
        for char in [".", "/", "\\", ":", "*", "?", '"', "<", ">", "|", " "]:
            safe_key = safe_key.replace(char, "_")
        return safe_key

    def _get_file_path(self, key: str) -> Path:
        """Get the file path for a given key."""
        safe_key = self._get_safe_key(key)
        filename = (
            f"{self.prefix}_{safe_key}.json" if self.prefix else f"{safe_key}.json"
        )
        return self.cache_dir / filename

    async def get(self, key: str) -> Any | None:
        """Get a value from storage by key.

        Args:
            key: The key to retrieve

        Returns:
            The stored value or None if not found
        """
        path = self._get_file_path(key)
        try:
            data = json.loads(path.read_text())
            logger.debug(f"Loaded data for key '{key}' from {path}")
            return data
        except FileNotFoundError:
            logger.debug(f"No data found for key '{key}'")
            return None
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Failed to load data for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Any) -> None:
        """Set a value in storage.

        Args:
            key: The key to store under
            value: The value to store (must be JSON-serializable)
        """
        path = self._get_file_path(key)

        # Handle Pydantic models
        if isinstance(value, BaseModel):
            json_data = value.model_dump_json(indent=2)
        else:
            json_data = json.dumps(value, indent=2, default=str)

        path.write_text(json_data)
        logger.debug(f"Saved data for key '{key}' to {path}")

    async def delete(self, key: str) -> None:
        """Delete a value from storage.

        Args:
            key: The key to delete
        """
        path = self._get_file_path(key)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted data for key '{key}'")

    async def clear(self) -> None:
        """Clear all stored values with this prefix."""
        pattern = f"{self.prefix}_*.json" if self.prefix else "*.json"
        for path in self.cache_dir.glob(pattern):
            path.unlink()
            logger.debug(f"Deleted {path}")
        logger.info(f"Cleared all stored values with prefix '{self.prefix}'")
