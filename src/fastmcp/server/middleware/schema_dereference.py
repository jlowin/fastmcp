from copy import deepcopy
from typing import Any

import mcp.types as mt

from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext


def _detect_self_reference(schema: dict) -> bool:
    """
    Detect if the schema contains self-referencing definitions.
    Args:
        schema: The JSON schema to check
    Returns:
        True if self-referencing is detected
    """
    defs = schema.get("$defs", {})

    def find_refs_in_value(value: Any, parent_def: str) -> bool:
        """Check if a value contains a reference to its parent definition."""
        if isinstance(value, dict):
            if "$ref" in value:
                ref_path = value["$ref"]
                # Check if this references the parent definition
                if ref_path == f"#/$defs/{parent_def}":
                    return True
            # Check all values in the dict
            for v in value.values():
                if find_refs_in_value(v, parent_def):
                    return True
        elif isinstance(value, list):
            # Check all items in the list
            for item in value:
                if find_refs_in_value(item, parent_def):
                    return True
        return False

    # Check each definition for self-reference
    for def_name, def_content in defs.items():
        if find_refs_in_value(def_content, def_name):
            # Self-reference detected, return original schema
            return True

    return False


def dereference_json_schema(schema: dict) -> dict:
    """
    Dereference a JSON schema by resolving $ref references while preserving $defs only when corner cases occur.
    This function flattens schema properties by:
    1. Check for self-reference - if found, return original schema with $defs
    2. When encountering $refs in properties, resolve them on-demand
    3. Track visited definitions globally to prevent circular expansion
    4. Only preserve original $defs if corner cases are encountered:
       - Self-reference detected
       - Circular references between definitions
       - Reference not found in $defs
    Args:
        schema: The JSON schema to flatten
    Returns:
        Schema with references resolved in properties, keeping $defs only when corner cases occur
    """
    # Step 1: Check for self-reference
    if _detect_self_reference(schema):
        # Self-referencing detected, return original schema with $defs
        return schema

    # Make a deep copy to work with
    result = deepcopy(schema)

    # Keep original $defs for potential corner cases
    defs = deepcopy(schema.get("$defs", {}))

    # Track corner cases that require preserving $defs
    corner_cases_detected = {
        "circular_ref": False,
        "ref_not_found": False,
    }

    # Step 2: Define resolution function that tracks visits globally and corner cases
    def resolve_refs_in_value(value: Any, depth: int, visiting: set[str]) -> Any:
        """
        Recursively resolve $refs in a value.
        Args:
            value: The value to process
            depth: Current depth in resolution
            visiting: Set of definitions currently being resolved (for cycle detection)
        Returns:
            Value with $refs resolved (or kept if corner cases occur)
        """
        if isinstance(value, dict):
            if "$ref" in value:
                ref_path = value["$ref"]

                # Only handle internal references to $defs
                if isinstance(ref_path, str) and ref_path.startswith("#/$defs/"):
                    def_name = ref_path.split("/")[-1]

                    # Check for circular reference
                    if def_name in visiting:
                        # Circular reference detected, keep the $ref
                        corner_cases_detected["circular_ref"] = True
                        return value

                    if def_name in defs:
                        # Add to visiting set
                        visiting.add(def_name)

                        # Get the definition and resolve any refs within it
                        resolved = resolve_refs_in_value(
                            deepcopy(defs[def_name]), depth + 1, visiting
                        )

                        # Remove from visiting set
                        visiting.remove(def_name)

                        # Merge resolved definition with additional properties
                        # Additional properties from the original object take precedence
                        for key, val in value.items():
                            if key != "$ref":
                                resolved[key] = val

                        return resolved
                    else:
                        # Definition not found, keep the $ref
                        corner_cases_detected["ref_not_found"] = True
                        return value
                else:
                    # External ref or other type - keep as is
                    return value
            else:
                # Regular dict - process all values
                return {
                    key: resolve_refs_in_value(val, depth, visiting)
                    for key, val in value.items()
                }
        elif isinstance(value, list):
            # Process each item in the list
            return [resolve_refs_in_value(item, depth, visiting) for item in value]
        else:
            # Primitive value - return as is
            return value

    # Step 3: Process main schema properties with shared visiting set
    for key, value in result.items():
        if key != "$defs":
            # Each top-level property gets its own visiting set
            # This allows the same definition to be used in different contexts
            result[key] = resolve_refs_in_value(value, 0, set())

    # Step 4: Conditionally preserve $defs based on corner cases
    if any(corner_cases_detected.values()):
        # Corner case detected, preserve original $defs
        if "$defs" in schema:  # Only add if original schema had $defs
            result["$defs"] = defs
    else:
        # No corner cases, remove $defs if it exists
        result.pop("$defs", None)

    return result


class SchemaDereferenceMiddleware(Middleware):
    """Middleware that dereferences $ref in schemas for tools, resource templates.

    Applies to list handlers so that clients like Claude Desktop receive flattened schemas
    without $ref in properties, preventing null parameter values.
    """

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, list],
    ) -> list:
        tools = await call_next(context)
        flattened = []
        for tool in tools:
            params = getattr(tool, "parameters", None)
            update: dict[str, Any] = {}
            if isinstance(params, dict):
                update["parameters"] = dereference_json_schema(params)
            if update:
                tool = tool.model_copy(update=update)
            flattened.append(tool)
        return flattened

    async def on_list_resource_templates(
        self,
        context: MiddlewareContext[mt.ListResourceTemplatesRequest],
        call_next: CallNext[mt.ListResourceTemplatesRequest, list],
    ) -> list:
        templates = await call_next(context)
        flattened = []
        for template in templates:
            params = getattr(template, "parameters", None)
            if isinstance(params, dict):
                template = template.model_copy(
                    update={"parameters": dereference_json_schema(params)}
                )
            flattened.append(template)
        return flattened
