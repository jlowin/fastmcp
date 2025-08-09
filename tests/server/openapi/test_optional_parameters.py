"""Test for optional parameter handling in FastMCP OpenAPI integration."""

import pytest

from fastmcp.utilities.openapi import HTTPRoute, ParameterInfo, _combine_schemas


async def test_optional_parameter_schema_preserves_original_type():
    """Test that optional parameters preserve their original schema without forcing nullable behavior."""
    # Create a minimal HTTPRoute with optional parameter
    optional_param = ParameterInfo(
        name="optional_param",
        location="query",
        required=False,
        schema={"type": "string"},
        description="Optional parameter",
    )

    required_param = ParameterInfo(
        name="required_param",
        location="query",
        required=True,
        schema={"type": "string"},
        description="Required parameter",
    )

    route = HTTPRoute(
        method="GET",
        path="/test",
        parameters=[required_param, optional_param],
        request_body=None,
        responses={},
        summary="Test endpoint",
        description=None,
        schema_definitions={},
    )

    # Generate combined schema
    schema = _combine_schemas(route)

    # Verify that optional parameter preserves original schema
    optional_param_schema = schema["properties"]["optional_param"]

    # Should preserve the original type without making it nullable
    assert optional_param_schema["type"] == "string"
    assert "anyOf" not in optional_param_schema

    # Required parameter should not allow null
    required_param_schema = schema["properties"]["required_param"]
    assert required_param_schema["type"] == "string"
    assert "anyOf" not in required_param_schema

    # Required list should only contain required param
    assert "required_param" in schema["required"]
    assert "optional_param" not in schema["required"]


@pytest.mark.parametrize(
    "param_schema",
    [
        {"type": "string"},
        {"type": "integer"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": {"name": {"type": "string"}}},
    ],
)
async def test_optional_parameter_preserves_schema_for_all_types(param_schema):
    """Test that optional parameters of any type preserve their original schema without nullable behavior."""
    optional_param = ParameterInfo(
        name="optional_param",
        location="query",
        required=False,
        schema=param_schema,
        description="Optional parameter",
    )

    route = HTTPRoute(
        method="GET",
        path="/test",
        parameters=[optional_param],
        request_body=None,
        responses={},
        summary="Test endpoint",
        description=None,
        schema_definitions={},
    )

    # Generate combined schema
    schema = _combine_schemas(route)
    optional_param_schema = schema["properties"]["optional_param"]

    # Should preserve the original schema exactly without making it nullable
    assert "anyOf" not in optional_param_schema

    # The schema should include the original type and fields, plus the description
    for key, value in param_schema.items():
        assert optional_param_schema[key] == value
    assert optional_param_schema.get("description") == "Optional parameter"


async def test_transitive_ref_dependencies_preserved():
    """Test that nested $refs are preserved in $defs when schemas reference other schemas transitively.

    This reproduces issue #1372 where Address was missing from $defs because:
    - User references Profile
    - Profile references Address
    - But only Profile was included in $defs, Address was pruned incorrectly
    """
    from fastmcp.utilities.openapi import RequestBodyInfo

    # Create schema definitions that reference each other
    schema_definitions = {
        "User": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "profile": {"$ref": "#/$defs/Profile"},
            },
            "required": ["id", "profile"],
        },
        "Profile": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "address": {"$ref": "#/$defs/Address"},
            },
            "required": ["name", "address"],
        },
        "Address": {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
                "city": {"type": "string"},
                "zipcode": {"type": "string"},
            },
            "required": ["street", "city", "zipcode"],
        },
    }

    # Create request body that references User
    request_body = RequestBodyInfo(
        required=True,
        content_schema={
            "application/json": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "profile": {"$ref": "#/$defs/Profile"},
                },
                "required": ["id", "profile"],
            }
        },
    )

    route = HTTPRoute(
        method="POST",
        path="/users",
        parameters=[],
        request_body=request_body,
        responses={},
        summary="Create a user",
        description=None,
        schema_definitions=schema_definitions,
    )

    # Generate combined schema
    schema = _combine_schemas(route)

    # Verify that all referenced schemas are preserved in $defs
    assert "$defs" in schema, "Schema should contain $defs section"

    defs = schema["$defs"]

    # All three schemas should be present because of transitive dependencies
    assert "Profile" in defs, "Profile should be in $defs (directly referenced)"
    assert "Address" in defs, "Address should be in $defs (referenced by Profile)"

    # Verify the schemas contain the expected structure
    profile_schema = defs["Profile"]
    assert profile_schema["properties"]["address"]["$ref"] == "#/$defs/Address"

    address_schema = defs["Address"]
    assert "street" in address_schema["properties"]
    assert "city" in address_schema["properties"]
    assert "zipcode" in address_schema["properties"]


async def test_deeper_transitive_ref_dependencies():
    """Test transitive dependencies work with deeper nesting levels."""
    from fastmcp.utilities.openapi import RequestBodyInfo

    # Create schema definitions with 4 levels of nesting
    schema_definitions = {
        "User": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "profile": {"$ref": "#/$defs/Profile"},
            },
            "required": ["id", "profile"],
        },
        "Profile": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "address": {"$ref": "#/$defs/Address"},
            },
            "required": ["name", "address"],
        },
        "Address": {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
                "location": {"$ref": "#/$defs/Location"},
            },
            "required": ["street", "location"],
        },
        "Location": {
            "type": "object",
            "properties": {"coordinates": {"$ref": "#/$defs/Coordinates"}},
            "required": ["coordinates"],
        },
        "Coordinates": {
            "type": "object",
            "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}},
            "required": ["lat", "lng"],
        },
        "UnusedSchema": {
            "type": "object",
            "properties": {"unused": {"type": "string"}},
        },
    }

    request_body = RequestBodyInfo(
        required=True,
        content_schema={
            "application/json": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "profile": {"$ref": "#/$defs/Profile"},
                },
                "required": ["id", "profile"],
            }
        },
    )

    route = HTTPRoute(
        method="POST",
        path="/users",
        parameters=[],
        request_body=request_body,
        responses={},
        summary="Create a user",
        description=None,
        schema_definitions=schema_definitions,
    )

    # Generate combined schema
    schema = _combine_schemas(route)

    # Verify that all transitively referenced schemas are preserved
    assert "$defs" in schema
    defs = schema["$defs"]

    # All nested schemas should be preserved
    assert "Profile" in defs, "Profile should be preserved (level 1)"
    assert "Address" in defs, "Address should be preserved (level 2)"
    assert "Location" in defs, "Location should be preserved (level 3)"
    assert "Coordinates" in defs, "Coordinates should be preserved (level 4)"

    # Unused schema should be removed
    assert "UnusedSchema" not in defs, "UnusedSchema should be removed"
