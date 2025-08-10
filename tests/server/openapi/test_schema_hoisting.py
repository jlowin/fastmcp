import pytest

from fastmcp.utilities.openapi import ResponseInfo, extract_output_schema_from_responses


@pytest.mark.asyncio
async def test_output_schema_hoisting_includes_nested_defs_legacy():
    # Minimal A -> B[] -> C reference chain
    # Main response schema A references B inside properties; B references C via $ref
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

    # Expect no dangling refs: both B and C must be present in $defs or inlined
    assert output is not None
    defs = output.get("$defs", {})
    # B should be present since A references B
    assert "B" in defs
    # C should also be present since B references C (nested)
    assert "C" in defs
