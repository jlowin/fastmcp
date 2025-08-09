"""Tests for the specific bugs reported in GitHub issue #1372."""

from fastmcp.experimental.utilities.openapi.models import (
    HTTPRoute,
    ParameterInfo,
    RequestBodyInfo,
    ResponseInfo,
)
from fastmcp.experimental.utilities.openapi.schemas import (
    _combine_schemas_and_map_params,
    extract_output_schema_from_responses,
)


class TestIssue1372Bugs:
    """Tests for the specific bugs reported in GitHub issue #1372."""

    def test_nested_refs_in_schema_definitions_not_converted(self):
        """$refs inside schema definitions should be converted from OpenAPI to JSON Schema format."""

        route = HTTPRoute(
            path="/users/{id}",
            method="POST",
            operation_id="create_user",
            parameters=[
                ParameterInfo(
                    name="id", location="path", required=True, schema={"type": "string"}
                )
            ],
            request_body=RequestBodyInfo(
                required=True,
                content_schema={
                    "application/json": {
                        "type": "object",
                        "properties": {"user": {"$ref": "#/components/schemas/User"}},
                    }
                },
            ),
            schema_definitions={
                "User": {
                    "type": "object",
                    "properties": {
                        "profile": {
                            "$ref": "#/components/schemas/Profile"
                        }  # This ref should be converted
                    },
                },
                "Profile": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        )

        combined_schema, _ = _combine_schemas_and_map_params(route)

        # Root level refs should be converted
        assert combined_schema["properties"]["user"]["$ref"] == "#/$defs/User"

        # Refs inside schema definitions should also be converted
        user_def = combined_schema["$defs"]["User"]
        assert user_def["properties"]["profile"]["$ref"] == "#/$defs/Profile"

    def test_transitive_dependencies_missing_from_response_schemas(self):
        """Reproduce the exact issue from #1372: Address schema missing from $defs."""

        # This mimics the exact structure reported in the issue
        responses = {
            "201": ResponseInfo(
                description="User created",
                content_schema={
                    "application/json": {"$ref": "#/components/schemas/User"}
                },
            )
        }

        schema_definitions = {
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "profile": {"$ref": "#/components/schemas/Profile"},
                },
                "required": ["id", "profile"],
            },
            "Profile": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "address": {
                        "$ref": "#/components/schemas/Address"
                    },  # Transitive ref
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

        result = extract_output_schema_from_responses(
            responses, schema_definitions=schema_definitions, openapi_version="3.0.3"
        )

        # The core issue: Address was being removed from $defs
        assert result is not None
        assert "$defs" in result
        assert "Profile" in result["$defs"], "Profile should be preserved"
        assert "Address" in result["$defs"], (
            "Address should be preserved (this was the main bug)"
        )

        # Refs should be converted to #/$defs format
        profile_def = result["$defs"]["Profile"]
        assert profile_def["properties"]["address"]["$ref"] == "#/$defs/Address"

    def test_transitive_refs_in_request_body_schemas(self):
        """Transitive $refs in request body schemas should be preserved and converted."""

        route = HTTPRoute(
            path="/users",
            method="POST",
            operation_id="create_user",
            request_body=RequestBodyInfo(
                required=True,
                content_schema={
                    "application/json": {"$ref": "#/components/schemas/User"}
                },
            ),
            schema_definitions={
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "profile": {
                            "$ref": "#/components/schemas/Profile"
                        },  # Nested ref
                    },
                    "required": ["id", "profile"],
                },
                "Profile": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "address": {
                            "$ref": "#/components/schemas/Address"
                        },  # Transitive ref
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
            },
        )

        combined_schema, _ = _combine_schemas_and_map_params(route)

        # All transitive dependencies should be preserved
        assert "User" in combined_schema["$defs"]
        assert "Profile" in combined_schema["$defs"]
        assert "Address" in combined_schema["$defs"]

        # All internal refs should be converted to #/$defs format
        user_def = combined_schema["$defs"]["User"]
        assert user_def["properties"]["profile"]["$ref"] == "#/$defs/Profile"

        profile_def = combined_schema["$defs"]["Profile"]
        assert profile_def["properties"]["address"]["$ref"] == "#/$defs/Address"

    def test_refs_in_array_items_not_converted(self):
        """$refs inside array items should be converted from OpenAPI to JSON Schema format."""

        route = HTTPRoute(
            path="/users",
            method="POST",
            operation_id="create_users",
            request_body=RequestBodyInfo(
                required=True,
                content_schema={
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "users": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/User"},
                            }
                        },
                    }
                },
            ),
            schema_definitions={
                "User": {
                    "type": "object",
                    "properties": {"profile": {"$ref": "#/components/schemas/Profile"}},
                },
                "Profile": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        )

        combined_schema, _ = _combine_schemas_and_map_params(route)

        # Array item refs should be converted
        assert combined_schema["properties"]["users"]["items"]["$ref"] == "#/$defs/User"

        # Nested refs should be converted
        user_def = combined_schema["$defs"]["User"]
        assert user_def["properties"]["profile"]["$ref"] == "#/$defs/Profile"

    def test_refs_in_composition_keywords_not_converted(self):
        """$refs inside oneOf/anyOf/allOf should be converted from OpenAPI to JSON Schema format."""

        route = HTTPRoute(
            path="/data",
            method="POST",
            operation_id="create_data",
            request_body=RequestBodyInfo(
                required=True,
                content_schema={
                    "application/json": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "oneOf": [
                                    {"$ref": "#/components/schemas/TypeA"},
                                    {"$ref": "#/components/schemas/TypeB"},
                                ]
                            }
                        },
                    }
                },
            ),
            schema_definitions={
                "TypeA": {
                    "type": "object",
                    "properties": {"nested": {"$ref": "#/components/schemas/Nested"}},
                },
                "TypeB": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
                "Nested": {"type": "string"},
            },
        )

        combined_schema, _ = _combine_schemas_and_map_params(route)

        # oneOf refs should be converted
        oneof_refs = combined_schema["properties"]["data"]["oneOf"]
        assert oneof_refs[0]["$ref"] == "#/$defs/TypeA"
        assert oneof_refs[1]["$ref"] == "#/$defs/TypeB"

        # Transitive refs should be converted
        type_a_def = combined_schema["$defs"]["TypeA"]
        assert type_a_def["properties"]["nested"]["$ref"] == "#/$defs/Nested"

    def test_deeply_nested_transitive_refs_pruned(self):
        """Deeply nested transitive refs should all be preserved."""

        route = HTTPRoute(
            path="/deep",
            method="POST",
            operation_id="create_deep",
            request_body=RequestBodyInfo(
                required=True,
                content_schema={
                    "application/json": {"$ref": "#/components/schemas/Level1"}
                },
            ),
            schema_definitions={
                "Level1": {
                    "type": "object",
                    "properties": {"level2": {"$ref": "#/components/schemas/Level2"}},
                },
                "Level2": {
                    "type": "object",
                    "properties": {"level3": {"$ref": "#/components/schemas/Level3"}},
                },
                "Level3": {
                    "type": "object",
                    "properties": {"level4": {"$ref": "#/components/schemas/Level4"}},
                },
                "Level4": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
                "UnusedSchema": {"type": "number"},
            },
        )

        combined_schema, _ = _combine_schemas_and_map_params(route)

        # All levels should be preserved
        assert "Level1" in combined_schema["$defs"]
        assert "Level2" in combined_schema["$defs"]
        assert "Level3" in combined_schema["$defs"]
        assert "Level4" in combined_schema["$defs"]

        # Unused should be removed
        assert "UnusedSchema" not in combined_schema["$defs"]

        # All refs should be converted
        assert (
            combined_schema["$defs"]["Level1"]["properties"]["level2"]["$ref"]
            == "#/$defs/Level2"
        )
        assert (
            combined_schema["$defs"]["Level2"]["properties"]["level3"]["$ref"]
            == "#/$defs/Level3"
        )
        assert (
            combined_schema["$defs"]["Level3"]["properties"]["level4"]["$ref"]
            == "#/$defs/Level4"
        )
