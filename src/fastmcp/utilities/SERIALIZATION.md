# Dual-Format Serialization Support

This module provides lightweight dual-format serialization support for FastMCP, allowing you to use either JSON (default) or TOON for structured data serialization.

## About TOON

**TOON (Token-Oriented Object Notation)** is a compact serialization format designed for passing structured data to Large Language Models with 30-60% token reduction compared to JSON.

- **Specification:** [github.com/toon-format/toon-spec](https://github.com/toon-format/toon-spec)
- **Reference Implementation:** [github.com/toon-format/toon](https://github.com/toon-format/toon) (TypeScript/JavaScript)
- **Version:** 2.0 (2025-11-10)
- **Sweet Spot:** Uniform arrays of objects with consistent structure

**Example:**

```
# JSON (98 tokens)
{"users": [{"id": 1, "name": "Alice", "role": "admin"}, {"id": 2, "name": "Bob", "role": "user"}]}

# TOON (48 tokens, ~51% reduction)
users[2]{id,name,role}:
  1,Alice,admin
  2,Bob,user
```

## Features

- **Backward Compatible**: JSON remains the default, all existing code continues to work
- **Zero Configuration**: Works out of the box with JSON
- **Optional TOON**: Enable TOON via environment variable or settings
- **Graceful Fallback**: Automatically falls back to JSON if TOON is unavailable
- **Extensible**: Designed to support additional formats in the future

## Quick Start

### Using JSON (Default)

No changes needed - FastMCP uses JSON by default:

```python
from fastmcp.utilities.serialization import serialize, deserialize

data = {"key": "value"}
serialized = serialize(data)  # JSON format
```

### Enabling TOON

**Via Environment Variable:**
```bash
export MCP_FORMAT=toon
```

**Via Settings:**
```python
from fastmcp import settings
settings.serialization_format = "toon"
```

**Via .env File:**
```
FASTMCP_SERIALIZATION_FORMAT=toon
```

### Installation

TOON support requires a Python implementation:

```bash
# Note: Check https://github.com/toon-format for Python implementations
# The reference implementation is TypeScript/JavaScript
pip install toon_format  # Available on PyPI
```

If no TOON package is available, the module gracefully falls back to JSON.

## API

- `serialize(data, fmt=None)` - Serialize Python data to string
- `deserialize(data, fmt=None)` - Deserialize string to Python object
- `is_toon_available()` - Check if TOON package is installed
- `get_active_format()` - Get currently active format name

## Implementation Details

- Located in `src/fastmcp/utilities/serialization.py`
- Tests in `tests/utilities/test_serialization.py`
- Documentation in `docs/patterns/toon-serialization.mdx`
- Example server in `examples/toon_example.py`

## Design Principles

1. **Minimal Changes**: One new utility module, minimal integration points
2. **No Breaking Changes**: Existing JSON behavior unchanged
3. **Token Efficient**: Lightweight abstraction with minimal overhead
4. **Environment Driven**: Runtime configuration via environment variables
5. **LLM Friendly**: TOON provides natural syntax for LLM consumption

## Testing

Run the serialization tests:

```bash
uv run pytest tests/utilities/test_serialization.py -xvs
```

All tests pass with TOON both available and unavailable (graceful fallback).

## Future Extensions

The abstraction layer can be extended to support additional formats:
- YAML
- TOML
- MessagePack
- Protocol Buffers

Simply add new format handlers to the serialize/deserialize functions.
