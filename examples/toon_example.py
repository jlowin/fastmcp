"""
Example demonstrating TOON serialization support in FastMCP.

This example shows how to use TOON as an alternative serialization format
for LLM-friendly structured data output with 30-60% token reduction.

TOON (Token-Oriented Object Notation) is designed for uniform arrays of objects.
Sweet spot: Multiple fields per row, same structure across items.

To enable TOON:
1. Check for Python implementation: https://github.com/toon-format
2. Install if available: pip install toon-format
3. Set environment: export MCP_FORMAT=toon
   OR configure via settings: settings.serialization_format = "toon"

The server will work with or without TOON installed, gracefully falling back to JSON.

Reference: https://github.com/toon-format/toon-spec (Spec v2.0)
"""

from fastmcp import FastMCP
from fastmcp.utilities.serialization import (
    deserialize,
    get_active_format,
    is_toon_available,
    serialize,
)

mcp = FastMCP("TOON Serialization Demo")


@mcp.tool
def check_serialization_status() -> dict:
    """Check which serialization format is active."""
    return {
        "toon_available": is_toon_available(),
        "active_format": get_active_format(),
        "formats_supported": ["json", "toon"],
    }


@mcp.tool
def serialize_example(data: dict) -> dict:
    """Serialize data using both JSON and TOON formats for comparison."""
    json_result = serialize(data, fmt="json")
    toon_result = serialize(data, fmt="toon") if is_toon_available() else "N/A"

    return {
        "original": data,
        "json": json_result,
        "toon": toon_result,
        "json_length": len(json_result),
        "toon_length": len(toon_result) if toon_result != "N/A" else 0,
    }


@mcp.tool
def demo_toon_sweet_spot() -> dict:
    """Demonstrate TOON's ideal use case: uniform arrays of objects."""
    # This is the kind of data TOON excels at
    users_data = [
        {"id": 1, "name": "Alice", "role": "admin", "active": True},
        {"id": 2, "name": "Bob", "role": "user", "active": True},
        {"id": 3, "name": "Charlie", "role": "user", "active": False},
    ]

    json_result = serialize(users_data, fmt="json")
    toon_result = (
        serialize(users_data, fmt="toon") if is_toon_available() else "N/A"
    )

    return {
        "description": "Uniform array with consistent structure - TOON's sweet spot",
        "data": users_data,
        "json": json_result,
        "json_length": len(json_result),
        "toon": toon_result,
        "toon_length": len(toon_result) if toon_result != "N/A" else 0,
        "token_savings": (
            f"{(1 - len(toon_result)/len(json_result)) * 100:.1f}%"
            if toon_result != "N/A"
            else "N/A"
        ),
    }


@mcp.tool
def demo_roundtrip(data: dict) -> dict:
    """Demonstrate serialization roundtrip with active format."""
    active_fmt = get_active_format()

    # Serialize
    serialized = serialize(data)

    # Deserialize
    deserialized = deserialize(serialized)

    return {
        "original": data,
        "format_used": active_fmt,
        "serialized": serialized,
        "deserialized": deserialized,
        "roundtrip_successful": data == deserialized,
    }


@mcp.resource("config://serialization")
def serialization_config() -> str:
    """Get current serialization configuration."""
    config = {
        "toon_installed": is_toon_available(),
        "active_format": get_active_format(),
        "spec_version": "TOON v2.0 (2025-11-10)",
        "reference": "https://github.com/toon-format/toon-spec",
        "sweet_spot": "Uniform arrays of objects with consistent structure",
        "token_savings": "Typically 30-60% vs JSON",
        "environment_hint": "Set MCP_FORMAT=toon to use TOON serialization",
        "implementation_note": "Reference implementation is TypeScript/JS",
    }
    return serialize(config)


if __name__ == "__main__":
    print("FastMCP TOON Serialization Demo")
    print("=" * 50)
    print(f"TOON Available: {is_toon_available()}")
    print(f"Active Format: {get_active_format()}")
    print()
    print("TOON Specification v2.0 (2025-11-10)")
    print("Sweet spot: Uniform arrays of objects")
    print("Token savings: Typically 30-60% vs JSON")
    print()
    print("Example usage:")
    print("  export MCP_FORMAT=toon  # Enable TOON")
    print("  fastmcp run toon_example.py")
    print()
    print("Reference: https://github.com/toon-format/toon-spec")
    print()

    mcp.run()
