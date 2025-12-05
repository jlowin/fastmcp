import copy

from fastmcp.server.middleware.schema_dereference import (
    dereference_json_schema,
)


def test_dereference_simple_enum_property_inlines_and_removes_defs():
    schema = {
        "$defs": {"Color": {"type": "string", "enum": ["red", "green", "blue"]}},
        "type": "object",
        "properties": {"color": {"$ref": "#/$defs/Color"}},
        "required": ["color"],
    }

    result = dereference_json_schema(copy.deepcopy(schema))

    assert "$defs" not in result
    assert "$ref" not in str(result)
    assert result["properties"]["color"]["enum"] == ["red", "green", "blue"]
    assert result["properties"]["color"]["type"] == "string"
    assert result["required"] == ["color"]


def test_dereference_merges_additional_properties():
    schema = {
        "$defs": {
            "Num": {"type": "number"},
        },
        "type": "object",
        "properties": {
            "n": {
                "$ref": "#/$defs/Num",
                "description": "a number",
                "minimum": 0,
            }
        },
    }

    result = dereference_json_schema(copy.deepcopy(schema))

    n_schema = result["properties"]["n"]
    assert n_schema["type"] == "number"
    assert n_schema["description"] == "a number"
    assert n_schema["minimum"] == 0
    assert "$defs" not in result


def test_dereference_allof_inlines_refs():
    schema = {
        "$defs": {
            "S": {"type": "string"},
        },
        "type": "object",
        "properties": {
            "val": {
                "allOf": [
                    {"$ref": "#/$defs/S"},
                    {"maxLength": 10},
                ]
            }
        },
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    allof = result["properties"]["val"]["allOf"]
    assert any(item.get("type") == "string" for item in allof)
    assert any(item.get("maxLength") == 10 for item in allof)
    assert "$defs" not in result


def test_dereference_keeps_schema_on_self_reference():
    schema = {
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"next": {"$ref": "#/$defs/Node"}},
            }
        },
        "type": "object",
        "properties": {"head": {"$ref": "#/$defs/Node"}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    # Self-reference: schema should be returned as-is to avoid expansion
    assert result == schema


def test_dereference_keeps_ref_and_preserves_defs_on_circular_refs():
    schema = {
        "$defs": {
            "A": {"$ref": "#/$defs/B"},
            "B": {"$ref": "#/$defs/A"},
        },
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/A"}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    # Circular: keep $ref and keep $defs
    assert result.get("$defs") == schema["$defs"]
    assert result["properties"]["x"]["$ref"] == "#/$defs/A"


def test_dereference_missing_ref_keeps_ref():
    schema = {
        "$defs": {"Something": {"type": "integer"}},
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/Missing"}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    # Missing ref: keep $ref, do not drop existing $defs
    assert result.get("$defs") == schema["$defs"]
    assert result["properties"]["x"]["$ref"] == "#/$defs/Missing"


def test_dereference_transitive_refs_are_inlined():
    schema = {
        "$defs": {
            "A": {"type": "object", "properties": {"b": {"$ref": "#/$defs/B"}}},
            "B": {"type": "string"},
        },
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/A"}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
    x_schema = result["properties"]["x"]
    assert x_schema["type"] == "object"
    assert x_schema["properties"]["b"]["type"] == "string"


def test_dereference_array_items_ref_inlined():
    schema = {
        "$defs": {"S": {"type": "string"}},
        "type": "object",
        "properties": {"arr": {"type": "array", "items": {"$ref": "#/$defs/S"}}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
    assert result["properties"]["arr"]["items"]["type"] == "string"


def test_dereference_additional_properties_ref_inlined():
    schema = {
        "$defs": {"S": {"type": "string"}},
        "type": "object",
        "properties": {
            "map": {
                "type": "object",
                "additionalProperties": {"$ref": "#/$defs/S"},
            }
        },
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
    assert (
        result["properties"]["map"]["additionalProperties"]["type"] == "string"
        and result["properties"]["map"]["type"] == "object"
    )


def test_dereference_oneof_and_anyof_refs_inlined():
    schema = {
        "$defs": {
            "S": {"type": "string"},
            "N": {"type": "number"},
        },
        "type": "object",
        "properties": {
            "v1": {"oneOf": [{"$ref": "#/$defs/S"}, {"$ref": "#/$defs/N"}]},
            "v2": {"anyOf": [{"$ref": "#/$defs/S"}, {"type": "boolean"}]},
        },
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
    oneof = result["properties"]["v1"]["oneOf"]
    anyof = result["properties"]["v2"]["anyOf"]
    assert any(item.get("type") == "string" for item in oneof)
    assert any(item.get("type") == "number" for item in oneof)
    assert any(item.get("type") == "string" for item in anyof)
    assert any(item.get("type") == "boolean" for item in anyof)


def test_dereference_reused_def_across_properties_inlined_independently():
    schema = {
        "$defs": {"S": {"type": "string"}},
        "type": "object",
        "properties": {
            "p1": {"$ref": "#/$defs/S"},
            "p2": {"$ref": "#/$defs/S"},
        },
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
    assert result["properties"]["p1"]["type"] == "string"
    assert result["properties"]["p2"]["type"] == "string"


def test_dereference_mixed_present_and_missing_refs_inlines_present_and_preserves_defs():
    schema = {
        "$defs": {"S": {"type": "string"}},
        "type": "object",
        "properties": {
            "ok": {"$ref": "#/$defs/S"},
            "bad": {"$ref": "#/$defs/Missing"},
        },
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    # Because of missing ref, defs are preserved
    assert "$defs" in result
    assert result["properties"]["ok"]["type"] == "string"
    assert result["properties"]["bad"]["$ref"] == "#/$defs/Missing"


def test_dereference_self_reference_in_def_array_items_returns_original():
    schema = {
        "$defs": {"Node": {"type": "array", "items": {"$ref": "#/$defs/Node"}}},
        "type": "object",
        "properties": {"head": {"$ref": "#/$defs/Node"}},
    }

    original = copy.deepcopy(schema)
    result = dereference_json_schema(schema)
    assert result == original


def test_dereference_nested_defs_with_allof_are_inlined():
    schema = {
        "$defs": {
            "Base": {"type": "object", "properties": {"a": {"type": "integer"}}},
            "Ext": {
                "allOf": [
                    {"$ref": "#/$defs/Base"},
                    {"type": "object", "properties": {"b": {"type": "string"}}},
                ]
            },
        },
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/Ext"}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
    x_schema = result["properties"]["x"]
    assert "allOf" in x_schema
    assert any(
        item.get("properties", {}).get("a", {}).get("type") == "integer"
        for item in x_schema["allOf"]
    )
    assert any(
        item.get("properties", {}).get("b", {}).get("type") == "string"
        for item in x_schema["allOf"]
    )


def test_dereference_removes_empty_defs_section():
    schema = {
        "$defs": {},
        "type": "object",
        "properties": {"n": {"type": "number"}},
    }

    result = dereference_json_schema(copy.deepcopy(schema))
    assert "$defs" not in result
