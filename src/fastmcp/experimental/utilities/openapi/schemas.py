"""Schema manipulation utilities for OpenAPI operations."""

from typing import Any

import msgspec

from fastmcp.utilities.logging import get_logger

from .models import HTTPRoute, JsonSchema, ResponseInfo

logger = get_logger(__name__)


def clean_schema_for_display(schema: JsonSchema | None) -> JsonSchema | None:
    """
    Clean up a schema dictionary for display by removing internal/complex fields.
    """
    if not schema or not isinstance(schema, dict):
        return schema

    # Make a copy to avoid modifying the input schema
    cleaned = schema.copy()

    # Fields commonly removed for simpler display to LLMs or users
    fields_to_remove = [
        "allOf",
        "anyOf",
        "oneOf",
        "not",  # Composition keywords
        "nullable",  # Handled by type unions usually
        "discriminator",
        "readOnly",
        "writeOnly",
        "deprecated",
        "xml",
        "externalDocs",
        # Can be verbose, maybe remove based on flag?
        # "pattern", "minLength", "maxLength",
        # "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        # "multipleOf", "minItems", "maxItems", "uniqueItems",
        # "minProperties", "maxProperties"
    ]

    for field in fields_to_remove:
        if field in cleaned:
            cleaned.pop(field)

    # Recursively clean properties and items
    if "properties" in cleaned:
        cleaned["properties"] = {
            k: clean_schema_for_display(v) for k, v in cleaned["properties"].items()
        }
        # Remove properties section if empty after cleaning
        if not cleaned["properties"]:
            cleaned.pop("properties")

    if "items" in cleaned:
        cleaned["items"] = clean_schema_for_display(cleaned["items"])
        # Remove items section if empty after cleaning
        if not cleaned["items"]:
            cleaned.pop("items")

    if "additionalProperties" in cleaned:
        # Often verbose, can be simplified
        if isinstance(cleaned["additionalProperties"], dict):
            cleaned["additionalProperties"] = clean_schema_for_display(
                cleaned["additionalProperties"]
            )
        elif cleaned["additionalProperties"] is True:
            # Maybe keep 'true' or represent as 'Allows additional properties' text?
            pass  # Keep simple boolean for now

    return cleaned


def _convert_refs_to_defs_format_simple(defs: dict[str, Any]) -> None:
    """
    Ultra-fast ref conversion using direct JSON processing.
    Converts #/components/schemas/X to #/$defs/X for all refs in schema definitions.

    Args:
        defs: Schema definitions dict to convert (modified in-place)
    """
    import re

    # Convert entire $defs to JSON string and check if it contains any refs
    defs_json = msgspec.json.encode(defs).decode("utf-8")

    # Quick check if there are any refs to replace - if not, skip entirely
    if "#/components/schemas/" not in defs_json:
        return

    # Single regex to replace all refs at once
    updated_json = re.sub(r'"#/components/schemas/([^"]+)"', r'"#/$defs/\1"', defs_json)

    # Parse back and update in place using msgspec
    updated_defs = msgspec.json.decode(updated_json.encode("utf-8"))
    defs.clear()
    defs.update(updated_defs)


def _make_optional_parameter_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Make an optional parameter schema nullable to allow None values.

    For optional parameters, we need to allow null values in addition to the
    specified type to handle cases where None is passed for optional parameters.
    """
    # If schema already has multiple types or is already nullable, don't modify
    if "anyOf" in schema or "oneOf" in schema or "allOf" in schema:
        return schema

    # If it's already nullable (type includes null), don't modify
    if isinstance(schema.get("type"), list) and "null" in schema["type"]:
        return schema

    # Create a new schema that allows null in addition to the original type
    if "type" in schema:
        original_type = schema["type"]
        if isinstance(original_type, str):
            # Handle different types appropriately
            if original_type in ("array", "object"):
                # For complex types (array/object), preserve the full structure
                # and allow null as an alternative
                if original_type == "array" and "items" in schema:
                    # Array with items - preserve items in anyOf branch
                    array_schema = schema.copy()
                    top_level_fields = ["default", "description", "title", "example"]
                    nullable_schema = {}

                    # Move top-level fields to the root
                    for field in top_level_fields:
                        if field in array_schema:
                            nullable_schema[field] = array_schema.pop(field)

                    nullable_schema["anyOf"] = [array_schema, {"type": "null"}]
                    return nullable_schema

                elif original_type == "object" and "properties" in schema:
                    # Object with properties - preserve properties in anyOf branch
                    object_schema = schema.copy()
                    top_level_fields = ["default", "description", "title", "example"]
                    nullable_schema = {}

                    # Move top-level fields to the root
                    for field in top_level_fields:
                        if field in object_schema:
                            nullable_schema[field] = object_schema.pop(field)

                    nullable_schema["anyOf"] = [object_schema, {"type": "null"}]
                    return nullable_schema
                else:
                    # Simple object/array without items/properties
                    nullable_schema = {}
                    original_schema = schema.copy()
                    top_level_fields = ["default", "description", "title", "example"]

                    for field in top_level_fields:
                        if field in original_schema:
                            nullable_schema[field] = original_schema.pop(field)

                    nullable_schema["anyOf"] = [original_schema, {"type": "null"}]
                    return nullable_schema
            else:
                # Simple types (string, integer, number, boolean)
                top_level_fields = ["default", "description", "title", "example"]
                nullable_schema = {}
                original_schema = schema.copy()

                for field in top_level_fields:
                    if field in original_schema:
                        nullable_schema[field] = original_schema.pop(field)

                nullable_schema["anyOf"] = [original_schema, {"type": "null"}]
                return nullable_schema

    return schema


def _combine_schemas_and_map_params(
    route: HTTPRoute,
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    """
    Combines parameter and request body schemas into a single schema.
    Handles parameter name collisions by adding location suffixes.
    Also returns parameter mapping for request director.

    Args:
        route: HTTPRoute object

    Returns:
        Tuple of (combined schema dictionary, parameter mapping)
        Parameter mapping format: {'flat_arg_name': {'location': 'path', 'openapi_name': 'id'}}
    """
    properties = {}
    required = []
    parameter_map = {}  # Track mapping from flat arg names to OpenAPI locations

    # First pass: collect parameter names by location and body properties
    param_names_by_location = {
        "path": set(),
        "query": set(),
        "header": set(),
        "cookie": set(),
    }
    body_props = {}

    for param in route.parameters:
        param_names_by_location[param.location].add(param.name)

    if route.request_body and route.request_body.content_schema:
        content_type = next(iter(route.request_body.content_schema))

        # Convert the entire request body schema from OpenAPI refs to JSON Schema refs
        body_schema_json = msgspec.json.encode(
            route.request_body.content_schema[content_type]
        ).decode("utf-8")
        body_schema_json = body_schema_json.replace("#/components/schemas/", "#/$defs/")
        body_schema = msgspec.json.decode(body_schema_json.encode("utf-8"))

        if route.request_body.description and not body_schema.get("description"):
            body_schema["description"] = route.request_body.description

        body_props = body_schema.get("properties", {})

    # Detect collisions: parameters that exist in both body and path/query/header
    all_non_body_params = set()
    for location_params in param_names_by_location.values():
        all_non_body_params.update(location_params)

    body_param_names = set(body_props.keys())
    colliding_params = all_non_body_params & body_param_names

    # Add parameters with suffixes for collisions
    for param in route.parameters:
        if param.name in colliding_params:
            # Add suffix for non-body parameters when collision detected
            suffixed_name = f"{param.name}__{param.location}"
            if param.required:
                required.append(suffixed_name)

            # Track parameter mapping
            parameter_map[suffixed_name] = {
                "location": param.location,
                "openapi_name": param.name,
            }

            # Convert refs in parameter schema
            param_schema_json = msgspec.json.encode(param.schema_).decode("utf-8")
            param_schema_json = param_schema_json.replace(
                "#/components/schemas/", "#/$defs/"
            )
            param_schema = msgspec.json.decode(param_schema_json.encode("utf-8"))
            original_desc = param_schema.get("description", "")
            location_desc = f"({param.location.capitalize()} parameter)"
            if original_desc:
                param_schema["description"] = f"{original_desc} {location_desc}"
            else:
                param_schema["description"] = location_desc

            # Don't make optional parameters nullable - they can simply be omitted
            # The OpenAPI specification doesn't require optional parameters to accept null values

            properties[suffixed_name] = param_schema
        else:
            # No collision, use original name
            if param.required:
                required.append(param.name)

            # Track parameter mapping
            parameter_map[param.name] = {
                "location": param.location,
                "openapi_name": param.name,
            }

            # Convert refs in parameter schema
            param_schema_json = msgspec.json.encode(param.schema_).decode("utf-8")
            param_schema_json = param_schema_json.replace(
                "#/components/schemas/", "#/$defs/"
            )
            param_schema = msgspec.json.decode(param_schema_json.encode("utf-8"))

            # Don't make optional parameters nullable - they can simply be omitted
            # The OpenAPI specification doesn't require optional parameters to accept null values

            properties[param.name] = param_schema

    # Add request body properties (no suffixes for body parameters)
    if route.request_body and route.request_body.content_schema:
        # If body is just a $ref, we need to handle it differently
        if "$ref" in body_schema and not body_props:
            # The entire body is a reference to a schema
            # We need to expand this inline or keep the ref
            # For simplicity, we'll keep it as a single property
            properties["body"] = body_schema
            if route.request_body.required:
                required.append("body")
            parameter_map["body"] = {"location": "body", "openapi_name": "body"}
        else:
            # Normal case: body has properties
            for prop_name, prop_schema in body_props.items():
                properties[prop_name] = prop_schema

                # Track parameter mapping for body properties
                parameter_map[prop_name] = {
                    "location": "body",
                    "openapi_name": prop_name,
                }

            if route.request_body.required:
                required.extend(body_schema.get("required", []))

    result = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    # Add schema definitions if available, converting refs throughout
    if route.schema_definitions:
        # Check if refs were already converted by the parser
        # If any ref still has the OpenAPI format, convert them all
        defs_str = str(route.schema_definitions)
        if "#/components/schemas/" in defs_str:
            # Convert ALL refs in schema definitions using string replacement
            defs_json = msgspec.json.encode(route.schema_definitions).decode("utf-8")
            defs_json = defs_json.replace("#/components/schemas/", "#/$defs/")
            result["$defs"] = msgspec.json.decode(defs_json.encode("utf-8"))
        else:
            # Already converted by parser, just use them
            result["$defs"] = route.schema_definitions

    # Prune unused definitions if we have any
    if "$defs" in result:
        used_refs = set()

        def find_refs_in_value(value):
            """Recursively find all $ref references."""
            if isinstance(value, dict):
                if "$ref" in value and isinstance(value["$ref"], str):
                    ref = value["$ref"]
                    if ref.startswith("#/$defs/"):
                        used_refs.add(ref.split("/")[-1])
                for v in value.values():
                    find_refs_in_value(v)
            elif isinstance(value, list):
                for item in value:
                    find_refs_in_value(item)

        # Find refs in the main schema (excluding $defs section)
        for key, value in result.items():
            if key != "$defs":
                find_refs_in_value(value)

        # Collect transitive dependencies
        if used_refs and result.get("$defs"):
            collected_all = False
            while not collected_all:
                initial_count = len(used_refs)

                # Check for refs within currently used schema definitions
                for name in list(used_refs):
                    if name in result["$defs"]:
                        find_refs_in_value(result["$defs"][name])

                # If no new refs found, we've collected all transitive dependencies
                collected_all = len(used_refs) == initial_count

        # Remove unused definitions
        if used_refs:
            result["$defs"] = {
                name: def_schema
                for name, def_schema in result["$defs"].items()
                if name in used_refs
            }
        else:
            # No refs used at all, remove $defs
            result.pop("$defs", None)

    return result, parameter_map


def _combine_schemas(route: HTTPRoute) -> dict[str, Any]:
    """
    Combines parameter and request body schemas into a single schema.
    Handles parameter name collisions by adding location suffixes.

    This is a backward compatibility wrapper around _combine_schemas_and_map_params.

    Args:
        route: HTTPRoute object

    Returns:
        Combined schema dictionary
    """
    schema, _ = _combine_schemas_and_map_params(route)
    return schema


def extract_output_schema_from_responses(
    responses: dict[str, ResponseInfo],
    schema_definitions: dict[str, Any] | None = None,
    openapi_version: str | None = None,
) -> dict[str, Any] | None:
    """
    Extract output schema from OpenAPI responses for use as MCP tool output schema.

    This function finds the first successful response (200, 201, 202, 204) with a
    JSON-compatible content type and extracts its schema. If the schema is not an
    object type, it wraps it to comply with MCP requirements.

    Args:
        responses: Dictionary of ResponseInfo objects keyed by status code
        schema_definitions: Optional schema definitions to include in the output schema
        openapi_version: OpenAPI version string, used to optimize nullable field handling

    Returns:
        dict: MCP-compliant output schema with potential wrapping, or None if no suitable schema found
    """
    if not responses:
        return None

    # Priority order for success status codes
    success_codes = ["200", "201", "202", "204"]

    # Find the first successful response
    response_info = None
    for status_code in success_codes:
        if status_code in responses:
            response_info = responses[status_code]
            break

    # If no explicit success codes, try any 2xx response
    if response_info is None:
        for status_code, resp_info in responses.items():
            if status_code.startswith("2"):
                response_info = resp_info
                break

    if response_info is None or not response_info.content_schema:
        return None

    # Prefer application/json, then fall back to other JSON-compatible types
    json_compatible_types = [
        "application/json",
        "application/vnd.api+json",
        "application/hal+json",
        "application/ld+json",
        "text/json",
    ]

    schema = None
    for content_type in json_compatible_types:
        if content_type in response_info.content_schema:
            schema = response_info.content_schema[content_type]
            break

    # If no JSON-compatible type found, try the first available content type
    if schema is None and response_info.content_schema:
        first_content_type = next(iter(response_info.content_schema))
        schema = response_info.content_schema[first_content_type]
        logger.debug(
            f"Using non-JSON content type for output schema: {first_content_type}"
        )

    if not schema or not isinstance(schema, dict):
        return None

    # Convert ALL refs in the schema using string replacement
    schema_json = msgspec.json.encode(schema).decode("utf-8")
    schema_json = schema_json.replace("#/components/schemas/", "#/$defs/")
    output_schema = msgspec.json.decode(schema_json.encode("utf-8"))

    # If schema has a $ref, resolve it first before processing nullable fields
    if "$ref" in output_schema and schema_definitions:
        ref_path = output_schema["$ref"]
        if ref_path.startswith("#/$defs/"):
            schema_name = ref_path.split("/")[-1]
            if schema_name in schema_definitions:
                # Replace $ref with the actual schema definition
                defs_json = msgspec.json.encode(schema_definitions[schema_name]).decode(
                    "utf-8"
                )
                defs_json = defs_json.replace("#/components/schemas/", "#/$defs/")
                output_schema = msgspec.json.decode(defs_json.encode("utf-8"))

    # Convert OpenAPI schema to JSON Schema format
    # Only needed for OpenAPI 3.0 - 3.1 uses standard JSON Schema null types
    if openapi_version and openapi_version.startswith("3.0"):
        from .json_schema_converter import convert_openapi_schema_to_json_schema

        output_schema = convert_openapi_schema_to_json_schema(
            output_schema, openapi_version
        )

    # MCP requires output schemas to be objects. If this schema is not an object,
    # we need to wrap it similar to how ParsedFunction.from_function() does it
    if output_schema.get("type") != "object":
        # Create a wrapped schema that contains the original schema under a "result" key
        wrapped_schema = {
            "type": "object",
            "properties": {"result": output_schema},
            "required": ["result"],
            "x-fastmcp-wrap-result": True,
        }
        output_schema = wrapped_schema

    # Add schema definitions if available
    # Always add them - we need them for transitive dependencies
    if schema_definitions:
        # Check if refs were already converted (e.g., by parser)
        defs_str = str(schema_definitions)
        if "#/components/schemas/" in defs_str:
            # Convert ALL refs in schema definitions using string replacement
            defs_json = msgspec.json.encode(schema_definitions).decode("utf-8")
            defs_json = defs_json.replace("#/components/schemas/", "#/$defs/")
            processed_defs = msgspec.json.decode(defs_json.encode("utf-8"))
        else:
            # Already converted, just use them
            processed_defs = schema_definitions

        # Convert OpenAPI schema definitions to JSON Schema format if needed
        if openapi_version and openapi_version.startswith("3.0"):
            from .json_schema_converter import convert_openapi_schema_to_json_schema

            for def_name in list(processed_defs.keys()):
                processed_defs[def_name] = convert_openapi_schema_to_json_schema(
                    processed_defs[def_name], openapi_version
                )

        output_schema["$defs"] = processed_defs

    # Prune unused definitions if we have any
    if "$defs" in output_schema:
        used_refs = set()

        def find_refs_in_value(value):
            """Recursively find all $ref references."""
            if isinstance(value, dict):
                if "$ref" in value and isinstance(value["$ref"], str):
                    ref = value["$ref"]
                    if ref.startswith("#/$defs/"):
                        used_refs.add(ref.split("/")[-1])
                for v in value.values():
                    find_refs_in_value(v)
            elif isinstance(value, list):
                for item in value:
                    find_refs_in_value(item)

        # Find refs in the main schema (excluding $defs section)
        for key, value in output_schema.items():
            if key != "$defs":
                find_refs_in_value(value)

        # Collect transitive dependencies
        if used_refs and output_schema.get("$defs"):
            collected_all = False
            while not collected_all:
                initial_count = len(used_refs)

                # Check for refs within currently used schema definitions
                for name in list(used_refs):
                    if name in output_schema["$defs"]:
                        find_refs_in_value(output_schema["$defs"][name])

                # If no new refs found, we've collected all transitive dependencies
                collected_all = len(used_refs) == initial_count

        # Remove unused definitions
        if used_refs:
            output_schema["$defs"] = {
                name: def_schema
                for name, def_schema in output_schema["$defs"].items()
                if name in used_refs
            }
        else:
            # No refs used at all, remove $defs
            output_schema.pop("$defs", None)

    return output_schema


# Export public symbols
__all__ = [
    "clean_schema_for_display",
    "_combine_schemas",
    "_combine_schemas_and_map_params",
    "extract_output_schema_from_responses",
    "_make_optional_parameter_nullable",
]
