"""Version comparison utilities for component versioning.

This module provides utilities for comparing component versions. Versions are
strings that are first attempted to be parsed as PEP 440 versions (using the
`packaging` library), falling back to lexicographic string comparison.

Examples:
    - "1", "2", "10" → parsed as PEP 440, compared semantically (1 < 2 < 10)
    - "1.0", "2.0" → parsed as PEP 440
    - "v1.0" → 'v' prefix stripped, parsed as "1.0"
    - "2025-01-15" → not valid PEP 440, compared as strings
    - None → sorts lowest (unversioned components)
"""

from __future__ import annotations

from functools import total_ordering
from typing import TYPE_CHECKING

from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from fastmcp.utilities.components import FastMCPComponent


@total_ordering
class VersionKey:
    """A comparable version key that handles None, PEP 440 versions, and strings.

    Comparison order:
    1. None (unversioned) sorts lowest
    2. PEP 440 versions sort by semantic version order
    3. Invalid versions (strings) sort lexicographically
    4. When comparing PEP 440 vs string, PEP 440 comes first
    """

    __slots__ = ("_is_none", "_is_pep440", "_parsed", "_raw")

    def __init__(self, version: str | None) -> None:
        self._raw = version
        self._is_none = version is None
        self._is_pep440 = False
        self._parsed: Version | str | None = None

        if version is not None:
            # Strip leading 'v' if present (common convention like "v1.0")
            normalized = version.lstrip("v") if version.startswith("v") else version
            try:
                self._parsed = Version(normalized)
                self._is_pep440 = True
            except InvalidVersion:
                # Fall back to string comparison for non-PEP 440 versions
                self._parsed = version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionKey):
            return NotImplemented
        if self._is_none and other._is_none:
            return True
        if self._is_none != other._is_none:
            return False
        # Both are not None
        if self._is_pep440 and other._is_pep440:
            return self._parsed == other._parsed
        if not self._is_pep440 and not other._is_pep440:
            return self._parsed == other._parsed
        # One is PEP 440, other is string - never equal
        return False

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, VersionKey):
            return NotImplemented
        # None sorts lowest
        if self._is_none and other._is_none:
            return False  # Equal
        if self._is_none:
            return True  # None < anything
        if other._is_none:
            return False  # anything > None

        # Both are not None
        if self._is_pep440 and other._is_pep440:
            # Both PEP 440 - compare normally
            assert isinstance(self._parsed, Version)
            assert isinstance(other._parsed, Version)
            return self._parsed < other._parsed
        if not self._is_pep440 and not other._is_pep440:
            # Both strings - lexicographic
            assert isinstance(self._parsed, str)
            assert isinstance(other._parsed, str)
            return self._parsed < other._parsed
        # Mixed: PEP 440 sorts before strings
        # (arbitrary but consistent choice)
        return self._is_pep440

    def __repr__(self) -> str:
        return f"VersionKey({self._raw!r})"


def parse_version_key(version: str | None) -> VersionKey:
    """Parse a version string into a sortable key.

    Args:
        version: The version string, or None for unversioned.

    Returns:
        A VersionKey suitable for sorting.
    """
    return VersionKey(version)


def version_sort_key(component: FastMCPComponent) -> VersionKey:
    """Get a sort key for a component based on its version.

    Use with sorted() or max() to order components by version.

    Args:
        component: The component to get a sort key for.

    Returns:
        A sortable VersionKey.

    Example:
        ```python
        tools = [tool_v1, tool_v2, tool_unversioned]
        highest = max(tools, key=version_sort_key)  # Returns tool_v2
        ```
    """
    return parse_version_key(component.version)


def compare_versions(a: str | None, b: str | None) -> int:
    """Compare two version strings.

    Args:
        a: First version string (or None).
        b: Second version string (or None).

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b.

    Example:
        ```python
        compare_versions("1.0", "2.0")  # Returns -1
        compare_versions("2.0", "1.0")  # Returns 1
        compare_versions(None, "1.0")   # Returns -1 (None < any version)
        ```
    """
    key_a = parse_version_key(a)
    key_b = parse_version_key(b)
    return (key_a > key_b) - (key_a < key_b)


def is_version_greater(a: str | None, b: str | None) -> bool:
    """Check if version a is greater than version b.

    Args:
        a: First version string (or None).
        b: Second version string (or None).

    Returns:
        True if a > b, False otherwise.
    """
    return compare_versions(a, b) > 0
