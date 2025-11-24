"""Simple vector store abstraction for tests."""
from __future__ import annotations

from collections.abc import Sequence
from typing import List


class VectorStore:
    def __init__(self) -> None:
        self._vectors: list[list[float]] = []

    def add(self, vector: Sequence[float]) -> None:
        self._vectors.append([float(x) for x in vector])

    def all(self) -> List[list[float]]:
        return [vec[:] for vec in self._vectors]
