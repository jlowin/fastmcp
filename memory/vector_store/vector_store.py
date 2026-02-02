"""Simple vector store abstraction for tests."""
from __future__ import annotations

from collections.abc import Sequence


class VectorStore:
    def __init__(self) -> None:
        self._vectors: list[list[float]] = []

    def add(self, vector: Sequence[float]) -> None:
        self._vectors.append([float(x) for x in vector])

    def all(self) -> list[list[float]]:
        return [vec[:] for vec in self._vectors]
