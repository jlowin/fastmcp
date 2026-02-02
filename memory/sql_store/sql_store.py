"""In-memory SQL-like store placeholder."""
from __future__ import annotations

from typing import Any


class SQLStore:
    """Very small key/value store used for diagnostics."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._data.get(key, default)

    def all(self) -> dict[str, Any]:
        return dict(self._data)
