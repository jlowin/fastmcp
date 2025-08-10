import pytest

from fastmcp.experimental.utilities.openapi.models import ResponseInfo
from fastmcp.experimental.utilities.openapi.schemas import (
    extract_output_schema_from_responses,
)


@pytest.mark.asyncio
async def test_output_schema_hoisting_includes_nested_defs_experimental():
    # Minimal A -> B[] -> C reference chain
    schema_definitions = {
        "B": {
            "type": "object",
            "properties": {
                "apps": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/C"},
                }
            },
            "required": ["apps"],
            "title": "B",
        },
        "C": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
            "title": "C",
        },
    }

    A = {
        "type": "object",
        "properties": {
            "plugins": {
                "type": "array",
                "items": {"$ref": "#/$defs/B"},
            }
        },
        "required": ["plugins"],
        "title": "A",
    }

    responses = {
        "200": ResponseInfo(description="ok", content_schema={"application/json": A})
    }

    output = extract_output_schema_from_responses(
        responses, schema_definitions=schema_definitions, openapi_version="3.1.0"
    )

    assert output is not None
    defs = output.get("$defs", {})
    assert "B" in defs
    assert "C" in defs


@pytest.mark.xfail(
    reason=(
        "Function-level builder expects parser to provide transitive schema_definitions;"
        " missing C violates contract"
    ),
    strict=False,
)
@pytest.mark.asyncio
async def test_output_schema_missing_nested_defs_is_fixed_experimental():
    # Minimal A -> B[] -> C, but schema_definitions only provides B (missing C)
    # Desired behavior: implementation should include C transitively when constructing $defs
    schema_definitions = {
        "B": {
            "type": "object",
            "properties": {
                "apps": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/C"},
                }
            },
            "required": ["apps"],
            "title": "B",
        }
    }

    A = {
        "type": "object",
        "properties": {
            "plugins": {
                "type": "array",
                "items": {"$ref": "#/$defs/B"},
            }
        },
        "required": ["plugins"],
        "title": "A",
    }

    responses = {
        "200": ResponseInfo(description="ok", content_schema={"application/json": A})
    }

    output = extract_output_schema_from_responses(
        responses, schema_definitions=schema_definitions, openapi_version="3.1.0"
    )

    assert output is not None
    defs = output.get("$defs", {})
    # Expected: both B and C present (C added transitively). This currently fails.
    assert "B" in defs
    assert "C" in defs
