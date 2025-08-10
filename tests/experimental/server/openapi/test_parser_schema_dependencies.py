import pytest

from fastmcp.experimental.utilities.openapi import parse_openapi_to_http_routes


def _make_minimal_openapi(spec_paths: dict, components: dict):
    # Minimal OpenAPI 3.1 wrapper for parser
    return {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1.0.0"},
        "paths": spec_paths,
        "components": {"schemas": components},
    }


@pytest.mark.asyncio
async def test_parser_includes_transitive_schema_dependencies():
    # A -> B[] -> C (transitive). Only B, C are components; A is inline on response.
    components = {
        "B": {
            "type": "object",
            "properties": {
                "apps": {"type": "array", "items": {"$ref": "#/components/schemas/C"}}
            },
            "required": ["apps"],
            "title": "B",
        },
        "C": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "title": "C",
        },
    }

    A = {
        "type": "object",
        "properties": {
            "plugins": {"type": "array", "items": {"$ref": "#/components/schemas/B"}}
        },
        "required": ["plugins"],
        "title": "A",
    }

    paths = {
        "/plugins": {
            "get": {
                "operationId": "get_plugins",
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {"application/json": {"schema": A}},
                    }
                },
            }
        }
    }

    routes = parse_openapi_to_http_routes(_make_minimal_openapi(paths, components))
    # Find our route
    route = next(r for r in routes if r.path == "/plugins" and r.method == "GET")
    # Expect both B and C present in schema_definitions for the route
    assert "B" in route.schema_definitions
    assert "C" in route.schema_definitions
