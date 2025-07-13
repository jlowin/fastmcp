"""Test for optional parameter handling in FastMCP OpenAPI integration."""

import pytest

from fastmcp.utilities.openapi import HTTPRoute, ParameterInfo, _combine_schemas


@pytest.mark.asyncio
async def test_optional_parameter_schema_allows_null():
    """Test that optional parameters generate schemas that allow null values."""
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

    # Verify that optional parameter allows null values
    optional_param_schema = schema["properties"]["optional_param"]

    # Should have anyOf with string and null types
    assert "anyOf" in optional_param_schema
    assert {"type": "string"} in optional_param_schema["anyOf"]
    assert {"type": "null"} in optional_param_schema["anyOf"]

    # Required parameter should not allow null
    required_param_schema = schema["properties"]["required_param"]
    assert required_param_schema["type"] == "string"
    assert "anyOf" not in required_param_schema

    # Required list should only contain required param
    assert "required_param" in schema["required"]
    assert "optional_param" not in schema["required"]


@pytest.mark.asyncio
async def test_optional_parameters_work_for_all_types():
    """Test that optional parameters of any type (not just string) allow null values."""
    test_cases = [
        {"type": "string"},
        {"type": "integer"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": {"name": {"type": "string"}}},
    ]

    for param_schema in test_cases:
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

        # Should have anyOf with the original type and null
        assert "anyOf" in optional_param_schema, f"Failed for type: {param_schema}"
        assert {"type": param_schema["type"]} in optional_param_schema[
            "anyOf"
        ] or param_schema in optional_param_schema["anyOf"], (
            f"Original type missing for: {param_schema}"
        )
        assert {"type": "null"} in optional_param_schema["anyOf"], (
            f"Null type missing for: {param_schema}"
        )
