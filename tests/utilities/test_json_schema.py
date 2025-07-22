from fastmcp.utilities.json_schema import (
    _detect_self_reference,
    _prune_param,
    compress_schema,
    dereference_json_schema,
)

# Wrapper for backward compatibility with tests


def _prune_additional_properties(schema):
    """Wrapper for compress_schema that only prunes additionalProperties: false."""
    return compress_schema(
        schema, prune_defs=False, prune_additional_properties=True, prune_titles=False
    )


class TestPruneParam:
    """Tests for the _prune_param function."""

    def test_nonexistent(self):
        """Test pruning a parameter that doesn't exist."""
        schema = {"properties": {"foo": {"type": "string"}}}
        result = _prune_param(schema, "bar")
        assert result == schema  # Schema should be unchanged

    def test_exists(self):
        """Test pruning a parameter that exists."""
        schema = {"properties": {"foo": {"type": "string"}, "bar": {"type": "integer"}}}
        result = _prune_param(schema, "bar")
        assert result["properties"] == {"foo": {"type": "string"}}

    def test_last_property(self):
        """Test pruning the only/last parameter, should leave empty properties object."""
        schema = {"properties": {"foo": {"type": "string"}}}
        result = _prune_param(schema, "foo")
        assert "properties" in result
        assert result["properties"] == {}

    def test_from_required(self):
        """Test pruning a parameter that's in the required list."""
        schema = {
            "properties": {"foo": {"type": "string"}, "bar": {"type": "integer"}},
            "required": ["foo", "bar"],
        }
        result = _prune_param(schema, "bar")
        assert result["required"] == ["foo"]

    def test_last_required(self):
        """Test pruning the last required parameter, should remove required field."""
        schema = {
            "properties": {"foo": {"type": "string"}, "bar": {"type": "integer"}},
            "required": ["foo"],
        }
        result = _prune_param(schema, "foo")
        assert "required" not in result


class TestPruneUnusedDefs:
    """Tests for unused definition pruning (via compress_schema)."""

    def test_removes_unreferenced_defs(self):
        """Test that unreferenced definitions are removed."""
        schema = {
            "properties": {
                "foo": {"$ref": "#/$defs/foo_def"},
            },
            "$defs": {
                "foo_def": {"type": "string"},
                "unused_def": {"type": "integer"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "foo_def" in result["$defs"]
        assert "unused_def" not in result["$defs"]

    def test_nested_references_kept(self):
        """Test that definitions referenced via nesting are kept."""
        schema = {
            "properties": {
                "foo": {"$ref": "#/$defs/foo_def"},
            },
            "$defs": {
                "foo_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/nested_def"}},
                },
                "nested_def": {"type": "string"},
                "unused_def": {"type": "integer"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "foo_def" in result["$defs"]
        assert "nested_def" in result["$defs"]
        assert "unused_def" not in result["$defs"]

    def test_nested_references_removed(self):
        """Test that definitions referenced via nesting in unused defs are removed."""
        schema = {
            "properties": {},
            "$defs": {
                "foo_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/nested_def"}},
                },
                "nested_def": {"type": "string"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "$defs" not in result

    def test_nested_references_with_recursion_kept(self):
        """Test that definitions with recursion referenced via nesting are kept."""
        schema = {
            "properties": {
                "foo": {"$ref": "#/$defs/foo_def"},
            },
            "$defs": {
                "foo_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/foo_def"}},
                },
                "unused_def": {"type": "integer"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "foo_def" in result["$defs"]
        assert "unused_def" not in result["$defs"]

    def test_nested_references_with_recursion_removed(self):
        """Test that definitions with recursion referenced via nesting in unused defs are removed."""
        schema = {
            "properties": {},
            "$defs": {
                "foo_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/foo_def"}},
                },
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "$defs" not in result

    def test_multiple_nested_references_with_recursion_kept(self):
        """Test that definitions with multiple levels of recursion referenced via nesting are kept."""
        schema = {
            "properties": {
                "foo": {"$ref": "#/$defs/foo_def"},
            },
            "$defs": {
                "foo_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/nested_def"}},
                },
                "nested_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/foo_def"}},
                },
                "unused_def": {"type": "integer"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "foo_def" in result["$defs"]
        assert "nested_def" in result["$defs"]
        assert "unused_def" not in result["$defs"]

    def test_multiple_nested_references_with_recursion_removed(self):
        """Test that definitions with multiple levels of recursion referenced via nesting in unused defs are removed."""
        schema = {
            "properties": {},
            "$defs": {
                "foo_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/nested_def"}},
                },
                "nested_def": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/$defs/foo_def"}},
                },
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "$defs" not in result

    def test_array_references_kept(self):
        """Test that definitions referenced in array items are kept."""
        schema = {
            "properties": {
                "items": {"type": "array", "items": {"$ref": "#/$defs/item_def"}},
            },
            "$defs": {
                "item_def": {"type": "string"},
                "unused_def": {"type": "integer"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "item_def" in result["$defs"]
        assert "unused_def" not in result["$defs"]

    def test_removes_defs_field_when_empty(self):
        """Test that $defs field is removed when all definitions are unused."""
        schema = {
            "properties": {
                "foo": {"type": "string"},
            },
            "$defs": {
                "unused_def": {"type": "integer"},
            },
        }
        result = compress_schema(
            schema,
            prune_defs=True,
            prune_additional_properties=False,
            prune_titles=False,
        )
        assert "$defs" not in result


class TestPruneAdditionalProperties:
    """Tests for the _prune_additional_properties function."""

    def test_removes_when_false(self):
        """Test that additionalProperties is removed when it's false."""
        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "additionalProperties": False,
        }
        result = _prune_additional_properties(schema)
        assert "additionalProperties" not in result

    def test_keeps_when_true(self):
        """Test that additionalProperties is kept when it's true."""
        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "additionalProperties": True,
        }
        result = _prune_additional_properties(schema)
        assert "additionalProperties" in result
        assert result["additionalProperties"] is True

    def test_keeps_when_object(self):
        """Test that additionalProperties is kept when it's an object schema."""
        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "additionalProperties": {"type": "string"},
        }
        result = _prune_additional_properties(schema)
        assert "additionalProperties" in result
        assert result["additionalProperties"] == {"type": "string"}


class TestCompressSchema:
    """Tests for the compress_schema function."""

    def test_prune_params(self):
        """Test pruning parameters with compress_schema."""
        schema = {
            "properties": {
                "foo": {"type": "string"},
                "bar": {"type": "integer"},
                "baz": {"type": "boolean"},
            },
            "required": ["foo", "bar"],
        }
        result = compress_schema(schema, prune_params=["foo", "baz"])
        assert result["properties"] == {"bar": {"type": "integer"}}
        assert result["required"] == ["bar"]

    def test_prune_defs(self):
        """Test pruning unused definitions with compress_schema."""
        schema = {
            "properties": {
                "foo": {"$ref": "#/$defs/foo_def"},
                "bar": {"type": "integer"},
            },
            "$defs": {
                "foo_def": {"type": "string"},
                "unused_def": {"type": "number"},
            },
        }
        result = compress_schema(schema)
        assert "foo_def" in result["$defs"]
        assert "unused_def" not in result["$defs"]

    def test_disable_prune_defs(self):
        """Test disabling pruning of unused definitions."""
        schema = {
            "properties": {
                "foo": {"$ref": "#/$defs/foo_def"},
                "bar": {"type": "integer"},
            },
            "$defs": {
                "foo_def": {"type": "string"},
                "unused_def": {"type": "number"},
            },
        }
        result = compress_schema(schema, prune_defs=False)
        assert "foo_def" in result["$defs"]
        assert "unused_def" in result["$defs"]

    def test_pruning_additional_properties(self):
        """Test pruning additionalProperties when False."""
        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "additionalProperties": False,
        }
        result = compress_schema(schema)
        assert "additionalProperties" not in result

    def test_disable_pruning_additional_properties(self):
        """Test disabling pruning of additionalProperties."""
        schema = {
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "additionalProperties": False,
        }
        result = compress_schema(schema, prune_additional_properties=False)
        assert "additionalProperties" in result
        assert result["additionalProperties"] is False

    def test_combined_operations(self):
        """Test all pruning operations together."""
        schema = {
            "type": "object",
            "properties": {
                "keep": {"type": "string"},
                "remove": {"$ref": "#/$defs/remove_def"},
            },
            "required": ["keep", "remove"],
            "additionalProperties": False,
            "$defs": {
                "remove_def": {"type": "string"},
                "unused_def": {"type": "number"},
            },
        }
        result = compress_schema(schema, prune_params=["remove"])
        # Check that parameter was removed
        assert "remove" not in result["properties"]
        # Check that required list was updated
        assert result["required"] == ["keep"]
        # Check that unused definitions were removed
        assert "$defs" not in result  # Both defs should be gone
        # Check that additionalProperties was removed
        assert "additionalProperties" not in result

    def test_prune_titles(self):
        """Test pruning title fields."""
        schema = {
            "title": "Root Schema",
            "type": "object",
            "properties": {
                "foo": {"title": "Foo Property", "type": "string"},
                "bar": {
                    "title": "Bar Property",
                    "type": "object",
                    "properties": {
                        "nested": {"title": "Nested Property", "type": "string"}
                    },
                },
            },
        }
        result = compress_schema(schema, prune_titles=True)
        assert "title" not in result
        assert "title" not in result["properties"]["foo"]
        assert "title" not in result["properties"]["bar"]
        assert "title" not in result["properties"]["bar"]["properties"]["nested"]

    def test_prune_nested_additional_properties(self):
        """Test pruning additionalProperties: false at all levels."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "foo": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "nested": {
                            "type": "object",
                            "additionalProperties": False,
                        }
                    },
                },
            },
        }
        result = compress_schema(schema)
        assert "additionalProperties" not in result
        assert "additionalProperties" not in result["properties"]["foo"]
        assert (
            "additionalProperties"
            not in result["properties"]["foo"]["properties"]["nested"]
        )


class TestDetectSelfReference:
    """Tests for the _detect_self_reference function."""

    def test_no_self_reference(self):
        """Test schema with normal references (no self-references)."""
        schema = {
            "$defs": {
                "Color": {"enum": ["red", "green", "blue"], "type": "string"},
                "Size": {"enum": ["small", "medium", "large"], "type": "string"},
            },
            "properties": {
                "color": {"$ref": "#/$defs/Color"},
                "size": {"$ref": "#/$defs/Size"},
            },
        }
        assert not _detect_self_reference(schema)

    def test_cross_references_not_self_references(self):
        """Test that cross-references (A->B->A) are not detected as self-references."""
        schema = {
            "$defs": {
                "A": {"type": "object", "properties": {"b": {"$ref": "#/$defs/B"}}},
                "B": {"type": "object", "properties": {"a": {"$ref": "#/$defs/A"}}},
            },
            "properties": {"root": {"$ref": "#/$defs/A"}},
        }
        assert not _detect_self_reference(schema)

    def test_direct_self_reference(self):
        """Test detection of direct self-reference (Node -> Node)."""
        schema = {
            "$defs": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/$defs/Node"}},
                }
            },
            "properties": {"root": {"$ref": "#/$defs/Node"}},
        }
        assert _detect_self_reference(schema)


class TestDereferenceJsonSchema:
    """Tests for the dereference_json_schema function."""

    def test_empty_schema(self):
        """Test dereferencing an empty schema."""
        schema = {}
        result = dereference_json_schema(schema)
        assert result == {}

    def test_schema_without_defs(self):
        """Test dereferencing a schema without $defs."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        }
        result = dereference_json_schema(schema)
        assert result == schema

    def test_basic_reference_resolution(self):
        """Test basic reference resolution removes $defs for simple schemas and resolves properties."""
        schema = {
            "$defs": {"Color": {"enum": ["red", "green", "blue"], "type": "string"}},
            "properties": {"color": {"$ref": "#/$defs/Color"}},
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "color": {"enum": ["red", "green", "blue"], "type": "string"}
            },
        }
        assert result == expected
        assert "$defs" not in result  # No corner cases, so $defs should be removed

    def test_max_depth_within_limit_removes_defs(self):
        """Test that staying within max_depth limit removes $defs (no corner case)."""
        # Create a 5-level chain with max_depth=6 (within limit)
        schema = {
            "$defs": {
                "Level1": {"$ref": "#/$defs/Level2"},
                "Level2": {"$ref": "#/$defs/Level3"},
                "Level3": {"$ref": "#/$defs/Level4"},
                "Level4": {"$ref": "#/$defs/Level5"},
                "Level5": {"type": "string", "maxLength": 100},
            },
            "properties": {"depth_field": {"$ref": "#/$defs/Level1"}},
        }
        result = dereference_json_schema(schema, max_depth=6)

        # Should resolve fully and remove $defs (within depth limit, no corner case)
        expected = {
            "properties": {"depth_field": {"type": "string", "maxLength": 100}},
        }
        assert result == expected
        assert "$defs" not in result  # Within limit, should resolve fully

        # Test with another case: 3-level chain with max_depth=4 (within limit)
        simple_chain = {
            "$defs": {
                "A": {"$ref": "#/$defs/B"},
                "B": {"$ref": "#/$defs/C"},
                "C": {"type": "integer", "minimum": 0},
            },
            "properties": {"value": {"$ref": "#/$defs/A"}},
        }
        simple_result = dereference_json_schema(simple_chain, max_depth=4)

        simple_expected = {
            "properties": {"value": {"type": "integer", "minimum": 0}},
        }
        assert simple_result == simple_expected
        assert "$defs" not in simple_result  # Within limit, should resolve fully

    def test_property_merging_during_resolution(self):
        """Test that additional properties are merged when resolving references."""
        schema = {
            "$defs": {"BaseString": {"type": "string", "minLength": 1}},
            "properties": {
                "name": {
                    "$ref": "#/$defs/BaseString",
                    "title": "Full Name",
                    "default": "Anonymous",
                    "maxLength": 100,
                }
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "title": "Full Name",
                    "default": "Anonymous",
                    "maxLength": 100,
                }
            },
        }
        assert result == expected
        assert "$defs" not in result  # Simple schema, no corner cases

    def test_references_in_allof_anyof_oneof(self):
        """Test dereferencing references within allOf, anyOf, and oneOf constructs."""
        schema = {
            "$defs": {
                "Animal": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
                "Dog": {"type": "object", "properties": {"breed": {"type": "string"}}},
                "Cat": {"type": "object", "properties": {"color": {"type": "string"}}},
            },
            "properties": {
                "pet_allof": {
                    "allOf": [{"$ref": "#/$defs/Animal"}, {"$ref": "#/$defs/Dog"}]
                },
                "pet_oneof": {
                    "oneOf": [{"$ref": "#/$defs/Dog"}, {"$ref": "#/$defs/Cat"}]
                },
            },
        }
        result = dereference_json_schema(schema)

        # Check that allOf references were resolved
        assert result["properties"]["pet_allof"]["allOf"][0]["type"] == "object"
        assert result["properties"]["pet_allof"]["allOf"][1]["type"] == "object"

        # Check that oneOf references were resolved
        assert result["properties"]["pet_oneof"]["oneOf"][0]["type"] == "object"
        assert result["properties"]["pet_oneof"]["oneOf"][1]["type"] == "object"

        assert "$defs" not in result  # Simple schema, no corner cases

    def test_references_in_conditional_schemas(self):
        """Test dereferencing references in if/then/else conditional schemas."""
        schema = {
            "$defs": {
                "StringType": {"type": "string"},
                "NumberType": {"type": "number"},
                "NamePattern": {"pattern": "^[A-Za-z]+$"},
            },
            "if": {"$ref": "#/$defs/StringType"},
            "then": {"$ref": "#/$defs/NamePattern"},
            "else": {"$ref": "#/$defs/NumberType"},
        }
        result = dereference_json_schema(schema)

        expected = {
            "if": {"type": "string"},
            "then": {"pattern": "^[A-Za-z]+$"},
            "else": {"type": "number"},
        }
        assert result == expected
        assert "$defs" not in result  # Simple schema, no corner cases

    # ===== Corner Cases (where $defs is preserved) =====

    def test_self_reference_preserves_defs(self):
        """Test that self-referencing schemas preserve $defs (corner case)."""
        schema = {
            "$defs": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/$defs/Node"}},
                }
            },
            "properties": {"root": {"$ref": "#/$defs/Node"}},
        }
        result = dereference_json_schema(schema)
        assert result == schema  # Should be unchanged due to self-reference
        assert "$defs" in result

    def test_circular_reference_preserves_defs(self):
        """Test that circular references preserve $defs (corner case)."""
        schema = {
            "$defs": {
                "NodeA": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "nodeB": {"$ref": "#/$defs/NodeB"},
                    },
                },
                "NodeB": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "integer"},
                        "nodeA": {"$ref": "#/$defs/NodeA"},  # Circular reference
                    },
                },
            },
            "properties": {"root": {"$ref": "#/$defs/NodeA"}},
        }
        result = dereference_json_schema(schema)
        assert "$defs" in result  # Corner case detected, $defs preserved

        # The function should do partial resolution but preserve circular refs
        # Original $defs should be unchanged
        assert result["$defs"] == schema["$defs"]

        # Root should be partially resolved but contain circular ref
        assert result["properties"]["root"]["type"] == "object"
        assert result["properties"]["root"]["properties"]["value"]["type"] == "string"
        assert "$ref" in str(
            result["properties"]["root"]["properties"]["nodeB"]["properties"]["nodeA"]
        )

    def test_missing_reference_preserves_defs(self):
        """Test that missing references preserve $defs (corner case)."""
        schema = {
            "$defs": {"Color": {"enum": ["red", "green", "blue"], "type": "string"}},
            "properties": {
                "color": {"$ref": "#/$defs/NonExistent"}
            },  # Missing reference
        }
        result = dereference_json_schema(schema)
        assert "$defs" in result  # Corner case detected, $defs preserved
        assert result["properties"]["color"] == {
            "$ref": "#/$defs/NonExistent"
        }  # Ref preserved

    def test_max_depth_exceeded_preserves_defs(self):
        """Test that exceeding max_depth preserves $defs (corner case)."""
        # Create a chain longer than max_depth (6 levels vs max_depth=5)
        schema = {
            "$defs": {
                "Level1": {"$ref": "#/$defs/Level2"},
                "Level2": {"$ref": "#/$defs/Level3"},
                "Level3": {"$ref": "#/$defs/Level4"},
                "Level4": {"$ref": "#/$defs/Level5"},
                "Level5": {"$ref": "#/$defs/Level6"},
                "Level6": {"type": "string", "maxLength": 100},
            },
            "properties": {"deep_field": {"$ref": "#/$defs/Level1"}},
        }
        result = dereference_json_schema(schema, max_depth=5)

        # Should preserve $defs when max_depth is exceeded (corner case detected)
        assert "$defs" in result
        assert "deep_field" in result["properties"]

        # Test with smaller max_depth to be more explicit
        result_small_depth = dereference_json_schema(schema, max_depth=2)
        assert "$defs" in result_small_depth  # Corner case: max_depth exceeded


class TestSchemaFlatteniingIntegration:
    """Tests for schema flattening through the public compress_schema API."""

    def test_integration_with_compress_schema(self):
        """Test that dereference_refs parameter works with compress_schema."""
        schema = {
            "$defs": {
                "Priority": {"enum": ["low", "medium", "high"], "type": "string"}
            },
            "properties": {
                "title": {"type": "string"},
                "priority": {"$ref": "#/$defs/Priority"},
                "context_param": {"type": "string"},  # This will be pruned
            },
            "required": ["title", "priority", "context_param"],
        }

        # Test with flattening enabled
        result = compress_schema(
            schema, prune_params=["context_param"], dereference_refs=True
        )

        expected = {
            "properties": {
                "title": {"type": "string"},
                "priority": {"enum": ["low", "medium", "high"], "type": "string"},
            },
            "required": ["title", "priority"],
        }
        assert result == expected
        assert "$defs" not in result  # Simple schema, no corner cases, so $defs removed
        assert "context_param" not in result["properties"]

    def test_compress_schema_with_self_references(self):
        """Test compress_schema behavior with self-referencing schemas."""
        schema = {
            "$defs": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "child": {"$ref": "#/$defs/Node"},
                    },
                }
            },
            "properties": {
                "tree": {"$ref": "#/$defs/Node"},
                "unused_param": {"type": "string"},
            },
            "required": ["tree", "unused_param"],
        }

        result = compress_schema(
            schema, prune_params=["unused_param"], dereference_refs=True
        )

        # Self-referencing schema should be returned with only parameter pruning applied
        expected = {
            "$defs": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "child": {"$ref": "#/$defs/Node"},
                    },
                }
            },
            "properties": {
                "tree": {"$ref": "#/$defs/Node"}  # Should remain as reference
            },
            "required": ["tree"],
        }
        assert result == expected

    def test_compress_schema_multiple_operations(self):
        """Test compress_schema with multiple operations including flattening."""
        schema = {
            "type": "object",
            "title": "TestSchema",
            "additionalProperties": False,
            "$defs": {
                "Status": {"enum": ["active", "inactive"], "type": "string"},
                "UnusedType": {"type": "number"},  # Will be pruned
            },
            "properties": {
                "name": {"type": "string", "title": "Name Field"},
                "status": {"$ref": "#/$defs/Status", "title": "Status Field"},
                "remove_me": {"type": "string"},  # Will be pruned
            },
            "required": ["name", "status", "remove_me"],
        }

        result = compress_schema(
            schema,
            prune_params=["remove_me"],
            prune_defs=True,
            prune_additional_properties=True,
            prune_titles=True,
            dereference_refs=True,
        )

        expected = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},  # Title removed
                "status": {
                    "enum": ["active", "inactive"],
                    "type": "string",
                },  # Flattened and title removed
            },
            "required": ["name", "status"],
            # additionalProperties: false should be removed
            # title should be removed
            # $defs removed since no corner cases
        }
        assert result == expected
        assert "title" not in result
        assert "additionalProperties" not in result
        assert "$defs" not in result  # No corner cases, so $defs removed entirely
        assert "remove_me" not in result["properties"]

    def test_deep_nesting_references(self):
        """Test dereferencing with multiple levels of nested references."""
        schema = {
            "$defs": {
                "Level3": {"type": "string", "enum": ["a", "b", "c"]},
                "Level2": {
                    "type": "object",
                    "properties": {"level3": {"$ref": "#/$defs/Level3"}},
                },
                "Level1": {
                    "type": "object",
                    "properties": {"level2": {"$ref": "#/$defs/Level2"}},
                },
            },
            "properties": {"root": {"$ref": "#/$defs/Level1"}},
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "root": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": {"type": "string", "enum": ["a", "b", "c"]}
                            },
                        }
                    },
                }
            },
        }
        assert result == expected
        assert "$defs" not in result  # Simple schema, no corner cases

    def test_mixed_refs_and_non_refs(self):
        """Test schema with mix of references and direct definitions."""
        schema = {
            "$defs": {"Status": {"enum": ["active", "inactive"], "type": "string"}},
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "status": {"$ref": "#/$defs/Status"},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "created": {"type": "string", "format": "date-time"}
                    },
                },
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "status": {"enum": ["active", "inactive"], "type": "string"},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "created": {"type": "string", "format": "date-time"}
                    },
                },
            },
        }
        assert result == expected
        assert "$defs" not in result  # Simple schema, no corner cases

    def test_reference_in_oneof(self):
        """Test dereferencing references within oneOf constructs."""
        schema = {
            "$defs": {
                "Dog": {"type": "object", "properties": {"breed": {"type": "string"}}},
                "Cat": {"type": "object", "properties": {"color": {"type": "string"}}},
            },
            "properties": {
                "pet": {"oneOf": [{"$ref": "#/$defs/Dog"}, {"$ref": "#/$defs/Cat"}]}
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "pet": {
                    "oneOf": [
                        {"type": "object", "properties": {"breed": {"type": "string"}}},
                        {"type": "object", "properties": {"color": {"type": "string"}}},
                    ]
                }
            },
        }
        assert result == expected

    def test_reference_in_allof(self):
        """Test dereferencing references within allOf constructs."""
        schema = {
            "$defs": {
                "Base": {"type": "object", "properties": {"id": {"type": "integer"}}},
                "Extended": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
            "properties": {
                "item": {
                    "allOf": [{"$ref": "#/$defs/Base"}, {"$ref": "#/$defs/Extended"}]
                }
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "item": {
                    "allOf": [
                        {"type": "object", "properties": {"id": {"type": "integer"}}},
                        {"type": "object", "properties": {"name": {"type": "string"}}},
                    ]
                }
            },
        }
        assert result == expected

    def test_property_override_precedence(self):
        """Test that properties in referring object take precedence over referenced ones."""
        schema = {
            "$defs": {
                "BaseType": {
                    "type": "string",
                    "title": "Base Title",
                    "description": "Base description",
                }
            },
            "properties": {
                "field": {
                    "$ref": "#/$defs/BaseType",
                    "title": "Override Title",  # This should override the base title
                    "default": "default_value",  # This should be added
                }
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "field": {
                    "title": "Override Title",  # Should keep the override
                    "default": "default_value",  # Should keep the additional property
                    "type": "string",  # Should get from base
                    "description": "Base description",  # Should get from base
                }
            },
        }
        assert result == expected

    def test_conditional_schemas_with_refs(self):
        """Test dereferencing with if/then/else containing references."""
        schema = {
            "$defs": {
                "StringType": {"type": "string"},
                "NumberType": {"type": "number"},
                "NamePattern": {"pattern": "^[A-Za-z]+$"},
            },
            "if": {"$ref": "#/$defs/StringType"},
            "then": {"$ref": "#/$defs/NamePattern"},
            "else": {"$ref": "#/$defs/NumberType"},
        }
        result = dereference_json_schema(schema)

        expected = {
            "if": {"type": "string"},
            "then": {"pattern": "^[A-Za-z]+$"},
            "else": {"type": "number"},
        }
        assert result == expected
        assert "$defs" not in result  # Simple schema, no corner cases

    def test_pattern_properties_with_refs(self):
        """Test dereferencing references within patternProperties."""
        schema = {
            "$defs": {
                "EmailType": {"type": "string", "format": "email"},
                "PhoneType": {"type": "string", "pattern": "^\\+?[1-9]\\d{1,14}$"},
            },
            "type": "object",
            "patternProperties": {
                "^email": {"$ref": "#/$defs/EmailType"},
                "^phone": {"$ref": "#/$defs/PhoneType"},
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "type": "object",
            "patternProperties": {
                "^email": {"type": "string", "format": "email"},
                "^phone": {"type": "string", "pattern": "^\\+?[1-9]\\d{1,14}$"},
            },
        }
        assert result == expected

    def test_additional_properties_with_refs(self):
        """Test dereferencing references in additionalProperties."""
        schema = {
            "$defs": {
                "FlexibleValue": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "boolean"},
                    ]
                }
            },
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": {"$ref": "#/$defs/FlexibleValue"},
        }
        result = dereference_json_schema(schema)

        expected = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": {
                "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
            },
        }
        assert result == expected

    def test_very_deep_reference_chain(self):
        """Test dereferencing a very deep chain of references (hits depth limit)."""
        schema = {
            "$defs": {
                "Level1": {"$ref": "#/$defs/Level2"},
                "Level2": {"$ref": "#/$defs/Level3"},
                "Level3": {"$ref": "#/$defs/Level4"},
                "Level4": {"$ref": "#/$defs/Level5"},
                "Level5": {"type": "string", "maxLength": 100},
            },
            "properties": {"deep_field": {"$ref": "#/$defs/Level1"}},
        }
        result = dereference_json_schema(schema)

        # Chain of 5 levels hits max_depth=5 limit, so should preserve $defs (corner case)
        expected = {
            "$defs": {
                "Level1": {"$ref": "#/$defs/Level2"},
                "Level2": {"$ref": "#/$defs/Level3"},
                "Level3": {"$ref": "#/$defs/Level4"},
                "Level4": {"$ref": "#/$defs/Level5"},
                "Level5": {"type": "string", "maxLength": 100},
            },
            "properties": {"deep_field": {"type": "string", "maxLength": 100}},
        }
        assert result == expected
        assert "$defs" in result  # Corner case: max_depth reached, $defs preserved

        # Test with higher max_depth to show it can be fully resolved
        result_high_depth = dereference_json_schema(schema, max_depth=10)
        expected_high_depth = {
            "properties": {"deep_field": {"type": "string", "maxLength": 100}},
        }
        assert result_high_depth == expected_high_depth
        assert "$defs" not in result_high_depth  # No corner case with higher limit

    def test_refs_with_additional_keywords_complex(self):
        """Test references combined with many additional keywords."""
        schema = {
            "$defs": {"BaseString": {"type": "string", "minLength": 1}},
            "properties": {
                "complex_field": {
                    "$ref": "#/$defs/BaseString",
                    "title": "Complex Field",
                    "description": "A field with many constraints",
                    "default": "default_value",
                    "examples": ["example1", "example2"],
                    "maxLength": 50,
                    "pattern": "^[a-zA-Z0-9]+$",
                    "format": "alphanumeric",
                }
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "complex_field": {
                    "title": "Complex Field",
                    "description": "A field with many constraints",
                    "default": "default_value",
                    "examples": ["example1", "example2"],
                    "maxLength": 50,
                    "pattern": "^[a-zA-Z0-9]+$",
                    "format": "alphanumeric",
                    "type": "string",  # From the referenced schema
                    "minLength": 1,  # From the referenced schema
                }
            },
        }
        assert result == expected

    def test_refs_in_complex_compositions(self):
        """Test references in complex schema compositions."""
        schema = {
            "$defs": {
                "Animal": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
                "Dog": {
                    "type": "object",
                    "properties": {
                        "breed": {"type": "string"},
                        "isGoodBoy": {"type": "boolean", "default": True},
                    },
                },
                "Cat": {
                    "type": "object",
                    "properties": {
                        "livesLeft": {"type": "integer", "minimum": 1, "maximum": 9}
                    },
                },
            },
            "properties": {
                "pet": {
                    "allOf": [
                        {"$ref": "#/$defs/Animal"},
                        {"anyOf": [{"$ref": "#/$defs/Dog"}, {"$ref": "#/$defs/Cat"}]},
                    ]
                }
            },
        }
        result = dereference_json_schema(schema)

        expected = {
            "properties": {
                "pet": {
                    "allOf": [
                        {"type": "object", "properties": {"name": {"type": "string"}}},
                        {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "breed": {"type": "string"},
                                        "isGoodBoy": {
                                            "type": "boolean",
                                            "default": True,
                                        },
                                    },
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "livesLeft": {
                                            "type": "integer",
                                            "minimum": 1,
                                            "maximum": 9,
                                        }
                                    },
                                },
                            ]
                        },
                    ]
                }
            },
        }
        assert result == expected
