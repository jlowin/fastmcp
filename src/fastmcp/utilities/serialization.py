"""Dual-format serialization support for FastMCP.

Supports JSON and TOON serialization. JSON is default; TOON can be enabled via MCP_FORMAT=toon.

This module provides a lightweight abstraction layer over serialization formats,
allowing FastMCP to use either JSON (default) or TOON (https://github.com/toon-format/toon)
for LLM-facing structured data while maintaining full backward compatibility with MCP clients.

TOON (Token-Oriented Object Notation) is designed for 30-60% token reduction when passing
uniform arrays of objects to LLMs. It's ideal for tabular data with consistent structure.
For deeply nested or non-uniform data, JSON may be more efficient.

Usage:
    # Default JSON serialization
    data = {"key": "value"}
    serialized = serialize(data)  # Uses JSON

    # Enable TOON via environment variable
    # export MCP_FORMAT=toon
    serialized = serialize(data)  # Uses TOON if available, falls back to JSON

    # Explicit format selection
    serialized = serialize(data, fmt="toon")
    deserialized = deserialize(serialized, fmt="toon")

Note: The reference TOON implementation is TypeScript/JavaScript. Python implementations
      may vary. If no Python TOON package is available, this module falls back to JSON.
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

# Runtime configuration: allows toggling between json and toon
# Priority: explicit fmt parameter > settings > environment variable > default (json)
MCP_FORMAT = os.getenv("MCP_FORMAT", "json").lower()

# Track TOON availability
_TOON_AVAILABLE = False
_TOON_IMPORT_ATTEMPTED = False
_toon_encode = None
_toon_decode = None

try:
    from toon_format import decode as toon_decode  # type: ignore[import-untyped]
    from toon_format import encode as toon_encode  # type: ignore[import-untyped]

    _toon_encode = toon_encode
    _toon_decode = toon_decode
    _TOON_AVAILABLE = True
    _TOON_IMPORT_ATTEMPTED = True
except ImportError:
    _TOON_IMPORT_ATTEMPTED = True
    if MCP_FORMAT == "toon":
        warnings.warn(
            "MCP_FORMAT=toon requested but 'toon_format' package is not installed. "
            "Falling back to JSON. Install with: pip install git+https://github.com/toon-format/toon-python.git",
            UserWarning,
            stacklevel=2,
        )


def _get_default_format() -> str:
    """Get the default format from settings or environment."""
    try:
        # Try to get format from settings (avoids circular import at module level)
        import fastmcp

        return fastmcp.settings.serialization_format
    except (ImportError, AttributeError):
        # Fall back to environment variable or default
        return MCP_FORMAT


def serialize(data: Any, fmt: str | None = None) -> str:
    """Serialize data to string using specified format.

    Args:
        data: Python object to serialize (dict, list, str, etc.)
        fmt: Format to use ('json' or 'toon'). If None, uses settings or MCP_FORMAT environment variable.

    Returns:
        Serialized string representation

    Raises:
        ValueError: If format is not supported
    """
    format_type = (fmt or _get_default_format()).lower()

    if format_type == "json":
        return json.dumps(data, separators=(",", ":"))
    elif format_type == "toon":
        if not _TOON_AVAILABLE or _toon_encode is None:
            if _TOON_IMPORT_ATTEMPTED:
                logger.warning(
                    "TOON format requested but not available. Falling back to JSON."
                )
            return json.dumps(data, separators=(",", ":"))
        return _toon_encode(data)
    else:
        raise ValueError(
            f"Unsupported serialization format: {format_type}. "
            f"Supported formats: json, toon"
        )


def deserialize(data: str, fmt: str | None = None) -> Any:
    """Deserialize string data to Python object using specified format.

    Args:
        data: Serialized string to deserialize
        fmt: Format to use ('json' or 'toon'). If None, uses settings or MCP_FORMAT environment variable.

    Returns:
        Deserialized Python object

    Raises:
        ValueError: If format is not supported
    """
    format_type = (fmt or _get_default_format()).lower()

    if format_type == "json":
        return json.loads(data)
    elif format_type == "toon":
        if not _TOON_AVAILABLE or _toon_decode is None:
            if _TOON_IMPORT_ATTEMPTED:
                logger.warning(
                    "TOON format requested but not available. Falling back to JSON."
                )
            return json.loads(data)
        return _toon_decode(data)
    else:
        raise ValueError(
            f"Unsupported deserialization format: {format_type}. "
            f"Supported formats: json, toon"
        )


def is_toon_available() -> bool:
    """Check if TOON serialization is available.

    Returns:
        True if toon package is installed, False otherwise
    """
    return _TOON_AVAILABLE


def get_active_format() -> str:
    """Get the currently active serialization format.

    Returns:
        'json' or 'toon' (falls back to json if toon unavailable)
    """
    format_type = _get_default_format()
    if format_type == "toon" and _TOON_AVAILABLE:
        return "toon"
    return "json"


__all__ = [
    "MCP_FORMAT",
    "deserialize",
    "get_active_format",
    "is_toon_available",
    "serialize",
]
