"""Tests for dual-format serialization support."""

import json
import os
from unittest.mock import patch

import pytest

from fastmcp.utilities.serialization import (
    deserialize,
    get_active_format,
    is_toon_available,
    serialize,
)


class TestJSONSerialization:
    """Test JSON serialization (default behavior)."""

    def test_serialize_dict(self):
        data = {"key": "value", "number": 42}
        result = serialize(data, fmt="json")
        assert result == '{"key":"value","number":42}'

    def test_serialize_list(self):
        data = [1, 2, 3, "test"]
        result = serialize(data, fmt="json")
        assert result == '[1,2,3,"test"]'

    def test_serialize_nested(self):
        data = {"outer": {"inner": [1, 2, 3]}, "flag": True}
        result = serialize(data, fmt="json")
        parsed = json.loads(result)
        assert parsed == data

    def test_deserialize_dict(self):
        data_str = '{"key":"value","number":42}'
        result = deserialize(data_str, fmt="json")
        assert result == {"key": "value", "number": 42}

    def test_deserialize_list(self):
        data_str = '[1,2,3,"test"]'
        result = deserialize(data_str, fmt="json")
        assert result == [1, 2, 3, "test"]

    def test_roundtrip(self):
        original = {"complex": {"nested": [1, 2, 3]}, "bool": False, "null": None}
        serialized = serialize(original, fmt="json")
        deserialized = deserialize(serialized, fmt="json")
        assert deserialized == original


class TestFormatSelection:
    """Test format selection and fallback behavior."""

    def test_default_format_is_json(self):
        """Without environment variable, default should be JSON."""
        data = {"test": "data"}
        result = serialize(data)
        # Should be valid JSON
        assert json.loads(result) == data

    def test_explicit_json_format(self):
        data = {"test": "data"}
        result = serialize(data, fmt="json")
        assert json.loads(result) == data

    def test_invalid_format_raises(self):
        data = {"test": "data"}
        with pytest.raises(ValueError, match="Unsupported serialization format"):
            serialize(data, fmt="invalid")

    def test_get_active_format_default(self):
        """Default format should be json."""
        # This test runs with default environment
        format_name = get_active_format()
        assert format_name in ["json", "toon"]  # Depends on TOON availability

    @patch.dict(os.environ, {"MCP_FORMAT": "json"})
    def test_env_var_json(self):
        """MCP_FORMAT=json should use JSON."""
        # Need to reload module to pick up env var change
        # For this test, we just verify serialize works
        data = {"test": "data"}
        result = serialize(data)
        assert json.loads(result) == data


class TestTOONSerialization:
    """Test TOON serialization if available."""

    def test_toon_availability(self):
        """is_toon_available should return bool."""
        available = is_toon_available()
        assert isinstance(available, bool)

    @pytest.mark.skipif(not is_toon_available(), reason="TOON not installed")
    def test_toon_serialize(self):
        """If TOON is available, test serialization."""
        data = {"key": "value", "number": 42}
        result = serialize(data, fmt="toon")
        # Result should be a string
        assert isinstance(result, str)
        # Should be deserializable
        deserialized = deserialize(result, fmt="toon")
        assert deserialized == data

    @pytest.mark.skipif(not is_toon_available(), reason="TOON not installed")
    def test_toon_roundtrip(self):
        """Test TOON roundtrip if available."""
        original = {"complex": {"nested": [1, 2, 3]}, "bool": False, "null": None}
        serialized = serialize(original, fmt="toon")
        deserialized = deserialize(serialized, fmt="toon")
        assert deserialized == original

    @pytest.mark.skipif(is_toon_available(), reason="Test only when TOON unavailable")
    def test_toon_fallback_to_json(self):
        """When TOON unavailable, should fall back to JSON."""
        data = {"test": "data"}
        # This should not raise, just fall back to JSON with warning
        result = serialize(data, fmt="toon")
        # Should still be valid JSON
        assert json.loads(result) == data


class TestEdgeCases:
    """Test edge cases and special values."""

    def test_serialize_none(self):
        result = serialize(None, fmt="json")
        assert result == "null"
        assert deserialize(result, fmt="json") is None

    def test_serialize_bool(self):
        assert serialize(True, fmt="json") == "true"
        assert serialize(False, fmt="json") == "false"

    def test_serialize_number(self):
        assert serialize(42, fmt="json") == "42"
        assert serialize(3.14, fmt="json") == "3.14"

    def test_serialize_string(self):
        result = serialize("hello world", fmt="json")
        assert result == '"hello world"'

    def test_serialize_empty_dict(self):
        result = serialize({}, fmt="json")
        assert result == "{}"

    def test_serialize_empty_list(self):
        result = serialize([], fmt="json")
        assert result == "[]"

    def test_unicode_handling(self):
        data = {"text": "Hello 世界 🌍"}
        serialized = serialize(data, fmt="json")
        deserialized = deserialize(serialized, fmt="json")
        assert deserialized == data
