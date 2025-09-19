"""Test title pruning functionality in compress_schema."""

from typing import Annotated

from pydantic import Field, TypeAdapter

from fastmcp.utilities.json_schema import compress_schema


def test_title_pruning_preserves_parameter_named_title():
    """Test that a parameter named 'title' is not removed during title pruning."""

    def greet(
        name: Annotated[str, Field(description="The name to greet")],
        title: Annotated[str, Field(description="Optional title", default="")],
    ) -> str:
        """A greeting function."""
        return f"Hello {title} {name}"

    adapter = TypeAdapter(greet)
    schema = adapter.json_schema()

    # Compress with title pruning
    compressed = compress_schema(schema, prune_titles=True)

    # The 'title' parameter should be preserved
    assert "title" in compressed["properties"]
    assert compressed["properties"]["title"]["description"] == "Optional title"
    assert compressed["properties"]["title"]["default"] == ""

    # But title metadata should be removed
    assert "title" not in compressed["properties"]["name"]
    assert "title" not in compressed["properties"]["title"]


def test_title_pruning_removes_schema_metadata_titles():
    """Test that title metadata fields are properly removed."""

    schema = {
        "type": "object",
        "title": "MySchema",
        "properties": {
            "field1": {
                "type": "string",
                "title": "Field One",
                "description": "First field",
            },
            "field2": {"type": "integer", "title": "Field Two"},
            "field3": {
                "$ref": "#/$defs/NestedType"  # Reference to keep $defs
            },
        },
        "$defs": {
            "NestedType": {
                "type": "object",
                "title": "Nested",
                "properties": {
                    "nested_field": {"type": "string", "title": "NestedField"}
                },
            }
        },
    }

    compressed = compress_schema(schema, prune_titles=True)

    # Root title should be removed
    assert "title" not in compressed

    # Property titles should be removed
    assert "title" not in compressed["properties"]["field1"]
    assert "title" not in compressed["properties"]["field2"]

    # But descriptions should be preserved
    assert compressed["properties"]["field1"]["description"] == "First field"

    # Definition titles should be removed if $defs is preserved
    if "$defs" in compressed:
        assert "title" not in compressed["$defs"]["NestedType"]
        assert (
            "title"
            not in compressed["$defs"]["NestedType"]["properties"]["nested_field"]
        )


def test_title_pruning_handles_nested_properties():
    """Test that nested property structures are handled correctly."""

    schema = {
        "type": "object",
        "title": "OuterObject",
        "properties": {
            "title": {  # This is a property named "title", not metadata
                "type": "object",
                "title": "TitleObject",  # This is metadata
                "properties": {
                    "subtitle": {
                        "type": "string",
                        "title": "SubTitle",  # This is metadata
                    }
                },
            },
            "normal_field": {
                "type": "string",
                "title": "NormalField",  # This is metadata
            },
        },
    }

    compressed = compress_schema(schema, prune_titles=True)

    # Root title should be removed
    assert "title" not in compressed

    # The property named "title" should be preserved
    assert "title" in compressed["properties"]

    # But its metadata title should be removed
    assert "title" not in compressed["properties"]["title"]

    # Nested metadata titles should be removed
    assert "title" not in compressed["properties"]["title"]["properties"]["subtitle"]
    assert "title" not in compressed["properties"]["normal_field"]


def test_title_pruning_disabled_by_default():
    """Test that title pruning is disabled by default."""

    schema = {
        "type": "object",
        "title": "TestSchema",
        "properties": {"field": {"type": "string", "title": "TestField"}},
    }

    # Without prune_titles, titles should be preserved
    compressed = compress_schema(schema)
    assert compressed["title"] == "TestSchema"
    assert compressed["properties"]["field"]["title"] == "TestField"

    # With prune_titles=False explicitly, titles should be preserved
    compressed = compress_schema(schema, prune_titles=False)
    assert compressed["title"] == "TestSchema"
    assert compressed["properties"]["field"]["title"] == "TestField"
