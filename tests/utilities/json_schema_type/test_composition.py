"""Tests for allOf/oneOf schema composition in JSON schema conversion.

Regression tests for https://github.com/PrefectHQ/fastmcp/issues/3839 —
``json_schema_to_type()`` silently returned ``typing.Any`` for ``allOf``
and ``oneOf`` schemas, disabling all validation.
"""

from typing import Any, Union, get_args, get_origin

import pytest
from pydantic import TypeAdapter, ValidationError

from fastmcp.utilities.json_schema_type import (
    json_schema_to_type,
)


class TestOneOf:
    """Test suite for oneOf unions.

    oneOf maps to the same Python representation as anyOf (a Union);
    exclusivity — rejecting values that match multiple sub-schemas — is
    not enforced.
    """

    @pytest.fixture
    def primitive_one_of(self):
        return json_schema_to_type({"oneOf": [{"type": "string"}, {"type": "integer"}]})

    @pytest.fixture
    def nullable_one_of(self):
        return json_schema_to_type({"oneOf": [{"type": "string"}, {"type": "null"}]})

    @pytest.fixture
    def object_one_of(self):
        return json_schema_to_type(
            {
                "oneOf": [
                    {
                        "type": "object",
                        "title": "Cat",
                        "properties": {"meow": {"type": "string"}},
                        "required": ["meow"],
                    },
                    {
                        "type": "object",
                        "title": "Dog",
                        "properties": {"bark": {"type": "string"}},
                        "required": ["bark"],
                    },
                ]
            }
        )

    def test_primitives_produce_union(self, primitive_one_of):
        assert get_origin(primitive_one_of) is Union
        assert set(get_args(primitive_one_of)) == {str, int}

    def test_primitives_accept_string(self, primitive_one_of):
        validator = TypeAdapter(primitive_one_of)
        assert validator.validate_python("test") == "test"

    def test_primitives_accept_integer(self, primitive_one_of):
        validator = TypeAdapter(primitive_one_of)
        assert validator.validate_python(42) == 42

    def test_primitives_reject_list(self, primitive_one_of):
        validator = TypeAdapter(primitive_one_of)
        with pytest.raises(ValidationError):
            validator.validate_python([1, 2])

    def test_null_member_produces_optional(self, nullable_one_of):
        validator = TypeAdapter(nullable_one_of)
        assert validator.validate_python("test") == "test"
        assert validator.validate_python(None) is None

    def test_null_member_rejects_other_types(self, nullable_one_of):
        validator = TypeAdapter(nullable_one_of)
        with pytest.raises(ValidationError):
            validator.validate_python(123)

    def test_object_members_accept_first_variant(self, object_one_of):
        validator = TypeAdapter(object_one_of)
        result = validator.validate_python({"meow": "loud"})
        assert result.meow == "loud"

    def test_object_members_accept_second_variant(self, object_one_of):
        validator = TypeAdapter(object_one_of)
        result = validator.validate_python({"bark": "loud"})
        assert result.bark == "loud"

    def test_object_members_reject_invalid(self, object_one_of):
        validator = TypeAdapter(object_one_of)
        with pytest.raises(ValidationError):
            validator.validate_python({"meow": 123, "bark": 456})

    def test_single_member_passes_through(self):
        result = json_schema_to_type({"oneOf": [{"type": "boolean"}]})
        assert result is bool


class TestAllOf:
    """Test suite for allOf schema merging."""

    @pytest.fixture
    def merged_objects(self):
        return json_schema_to_type(
            {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                    {
                        "type": "object",
                        "properties": {"age": {"type": "integer"}},
                        "required": ["age"],
                    },
                ]
            }
        )

    @pytest.fixture
    def ref_composition(self):
        return json_schema_to_type(
            {
                "allOf": [
                    {"$ref": "#/$defs/Base"},
                    {
                        "type": "object",
                        "properties": {"extra": {"type": "boolean"}},
                    },
                ],
                "$defs": {
                    "Base": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                    }
                },
            }
        )

    @pytest.fixture
    def constrained_string(self):
        return json_schema_to_type({"allOf": [{"type": "string"}, {"minLength": 3}]})

    def test_merged_objects_have_all_properties(self, merged_objects):
        field_names = set(merged_objects.__dataclass_fields__)
        assert field_names == {"name", "age"}

    def test_merged_objects_accept_valid_data(self, merged_objects):
        validator = TypeAdapter(merged_objects)
        result = validator.validate_python({"name": "Alice", "age": 30})
        assert result.name == "Alice"
        assert result.age == 30

    def test_merged_required_from_both_subschemas(self, merged_objects):
        validator = TypeAdapter(merged_objects)
        with pytest.raises(ValidationError):
            validator.validate_python({"name": "Alice"})
        with pytest.raises(ValidationError):
            validator.validate_python({"age": 30})

    def test_merged_objects_reject_wrong_types(self, merged_objects):
        validator = TypeAdapter(merged_objects)
        with pytest.raises(ValidationError):
            validator.validate_python({"name": "Alice", "age": "not a number"})

    def test_ref_subschema_merged(self, ref_composition):
        validator = TypeAdapter(ref_composition)
        result = validator.validate_python({"id": 1, "extra": True})
        assert result.id == 1
        assert result.extra is True

    def test_ref_subschema_required_enforced(self, ref_composition):
        validator = TypeAdapter(ref_composition)
        with pytest.raises(ValidationError):
            validator.validate_python({"extra": True})

    def test_constraints_merged_onto_type(self, constrained_string):
        validator = TypeAdapter(constrained_string)
        assert validator.validate_python("abc") == "abc"

    def test_constraints_merged_reject_invalid(self, constrained_string):
        validator = TypeAdapter(constrained_string)
        with pytest.raises(ValidationError):
            validator.validate_python("ab")

    def test_single_item_passes_through(self):
        result = json_schema_to_type({"allOf": [{"type": "integer"}]})
        assert result is int

    def test_true_subschema_adds_no_constraints(self):
        result = json_schema_to_type({"allOf": [{"type": "string"}, True]})
        assert result is str

    def test_false_subschema_is_unsatisfiable(self):
        result = json_schema_to_type({"allOf": [{"type": "string"}, False]})
        validator = TypeAdapter(result)
        with pytest.raises(ValidationError):
            validator.validate_python("anything")

    def test_self_referencing_all_of_ref_does_not_crash(self):
        # A $ref cycle inside allOf cannot be represented as a flat merged
        # schema; the cyclic member degrades to no constraints instead of
        # raising RecursionError.
        schema = {
            "$ref": "#/$defs/Node",
            "$defs": {
                "Node": {
                    "allOf": [
                        {"$ref": "#/$defs/Node"},
                        {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                            "required": ["value"],
                        },
                    ]
                }
            },
        }
        result = json_schema_to_type(schema)
        validator = TypeAdapter(result)
        validated: Any = validator.validate_python({"value": 1})
        assert validated.value == 1
        with pytest.raises(ValidationError):
            validator.validate_python({})

    def test_chained_ref_composition_preserves_all_members(self):
        schema = {
            "allOf": [
                {"$ref": "#/$defs/Alias"},
                {
                    "type": "object",
                    "properties": {"extra": {"type": "boolean"}},
                    "required": ["extra"],
                },
            ],
            "$defs": {
                "Alias": {"$ref": "#/$defs/Base"},
                "Base": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}},
                    "required": ["id"],
                },
            },
        }
        validator = TypeAdapter(json_schema_to_type(schema))
        result: Any = validator.validate_python({"id": 1, "extra": True})
        assert result.id == 1
        assert result.extra is True
        with pytest.raises(ValidationError):
            validator.validate_python({"id": 1})
        with pytest.raises(ValidationError):
            validator.validate_python({"extra": True})

    def test_ref_member_siblings_apply_conjunctively(self):
        # Per JSON Schema 2020-12, keys alongside $ref apply in addition
        # to the referenced schema.
        schema = {
            "allOf": [{"$ref": "#/$defs/Str", "minLength": 3}],
            "$defs": {"Str": {"type": "string"}},
        }
        validator = TypeAdapter(json_schema_to_type(schema))
        assert validator.validate_python("abc") == "abc"
        with pytest.raises(ValidationError):
            validator.validate_python("ab")

    def test_ref_resolving_to_true_schema(self):
        schema = {
            "allOf": [{"$ref": "#/$defs/Anything"}, {"type": "string"}],
            "$defs": {"Anything": True},
        }
        assert json_schema_to_type(schema) is str

    def test_ref_resolving_to_false_schema_is_unsatisfiable(self):
        schema = {
            "allOf": [{"$ref": "#/$defs/Nothing"}, {"type": "string"}],
            "$defs": {"Nothing": False},
        }
        validator = TypeAdapter(json_schema_to_type(schema))
        with pytest.raises(ValidationError):
            validator.validate_python("anything")

    def test_top_level_all_of_supports_name(self):
        schema = {
            "allOf": [
                {"type": "object", "properties": {"a": {"type": "string"}}},
                {"type": "object", "properties": {"b": {"type": "integer"}}},
            ]
        }
        result = json_schema_to_type(schema, name="Merged")
        assert result.__name__ == "Merged"

    def test_sibling_properties_participate_in_merge(self):
        schema = {
            "allOf": [{"type": "object", "properties": {"a": {"type": "string"}}}],
            "properties": {"b": {"type": "integer"}},
            "required": ["b"],
        }
        result = json_schema_to_type(schema)
        validator = TypeAdapter(result)
        merged: Any = validator.validate_python({"a": "x", "b": 1})
        assert merged.a == "x"
        assert merged.b == 1
        with pytest.raises(ValidationError):
            validator.validate_python({"a": "x"})


class TestNestedComposition:
    """Test suite for composition keywords nested inside each other."""

    def test_all_of_inside_one_of(self):
        schema = {
            "oneOf": [
                {"allOf": [{"type": "string"}, {"minLength": 3}]},
                {"type": "integer"},
            ]
        }
        validator = TypeAdapter(json_schema_to_type(schema))
        assert validator.validate_python("abc") == "abc"
        assert validator.validate_python(42) == 42
        with pytest.raises(ValidationError):
            validator.validate_python("ab")

    def test_one_of_inside_property(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"oneOf": [{"type": "string"}, {"type": "integer"}]}
            },
            "required": ["value"],
        }
        validator = TypeAdapter(json_schema_to_type(schema))
        string_result: Any = validator.validate_python({"value": "x"})
        assert string_result.value == "x"
        integer_result: Any = validator.validate_python({"value": 1})
        assert integer_result.value == 1
        with pytest.raises(ValidationError):
            validator.validate_python({"value": [1]})

    def test_all_of_inside_property(self):
        schema = {
            "type": "object",
            "properties": {
                "item": {
                    "allOf": [
                        {"type": "object", "properties": {"x": {"type": "integer"}}},
                        {"type": "object", "properties": {"y": {"type": "integer"}}},
                    ]
                }
            },
            "required": ["item"],
        }
        validator = TypeAdapter(json_schema_to_type(schema))
        result: Any = validator.validate_python({"item": {"x": 1, "y": 2}})
        assert result.item.x == 1
        assert result.item.y == 2


class TestIssue3839Regression:
    """The exact MREs from issue #3839 must not return Any."""

    def test_all_of_mre_not_any(self):
        schema = {
            "allOf": [
                {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                {"type": "object", "properties": {"age": {"type": "integer"}}},
            ]
        }
        result = json_schema_to_type(schema)
        assert result is not Any

    def test_one_of_mre_not_any(self):
        schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
        result = json_schema_to_type(schema)
        assert result is not Any
