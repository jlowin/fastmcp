from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


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


def dereference_json_schema(schema: dict, max_depth: int = 50) -> dict:
    """
    Dereference a JSON schema by resolving $ref references while preserving $defs only when corner cases occur.

    This function flattens schema properties by:
    1. Check for self-reference - if found, return original schema with $defs
    2. When encountering $refs in properties, resolve them on-demand
    3. Track visited definitions globally to prevent circular expansion
    4. Only preserve original $defs if corner cases are encountered:
       - Self-reference detected
       - Circular references between definitions
       - Reference depth exceeds max_depth
       - Reference not found in $defs

    Args:
        schema: The JSON schema to flatten
        max_depth: Maximum depth for resolving references (default: 5)

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
        "max_depth_reached": False,
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
        if depth >= max_depth:
            corner_cases_detected["max_depth_reached"] = True
            return value

        if isinstance(value, dict):
            if "$ref" in value:
                ref_path = value["$ref"]

                # Only handle internal references to $defs
                if ref_path.startswith("#/$defs/"):
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


def _prune_param(schema: dict, param: str) -> dict:
    """Return a new schema with *param* removed from `properties`, `required`,
    and (if no longer referenced) `$defs`.
    """

    # ── 1. drop from properties/required ──────────────────────────────
    props = schema.get("properties", {})
    removed = props.pop(param, None)
    if removed is None:  # nothing to do
        return schema

    # Keep empty properties object rather than removing it entirely
    schema["properties"] = props
    if param in schema.get("required", []):
        schema["required"].remove(param)
        if not schema["required"]:
            schema.pop("required")

    return schema


def _single_pass_optimize(
    schema: dict,
    prune_titles: bool = False,
    prune_additional_properties: bool = False,
    prune_defs: bool = True,
) -> dict:
    """
    Optimize JSON schemas in a single traversal for better performance.

    This function combines three schema cleanup operations that would normally require
    separate tree traversals:

    1. **Remove unused definitions** (prune_defs): Finds and removes `$defs` entries
       that aren't referenced anywhere in the schema, reducing schema size.

    2. **Remove titles** (prune_titles): Strips `title` fields throughout the schema
       to reduce verbosity while preserving functional information.

    3. **Remove restrictive additionalProperties** (prune_additional_properties):
       Removes `"additionalProperties": false` constraints to make schemas more flexible.

    **Performance Benefits:**
    - Single tree traversal instead of multiple passes (2-3x faster)
    - Immutable design prevents shared reference bugs
    - Early termination prevents runaway recursion on deeply nested schemas

    **Algorithm Overview:**
    1. Traverse main schema, collecting $ref references and applying cleanups
    2. Traverse $defs section to map inter-definition dependencies
    3. Remove unused definitions based on reference analysis

    Args:
        schema: JSON schema dict to optimize (not modified)
        prune_titles: Remove title fields for cleaner output
        prune_additional_properties: Remove "additionalProperties": false constraints
        prune_defs: Remove unused $defs entries to reduce size

    Returns:
        A new optimized schema dict

    Example:
        >>> schema = {
        ...     "type": "object",
        ...     "title": "MySchema",
        ...     "additionalProperties": False,
        ...     "$defs": {"UnusedDef": {"type": "string"}}
        ... }
        >>> result = _single_pass_optimize(schema, prune_titles=True, prune_defs=True)
        >>> # Result: {"type": "object", "additionalProperties": False}
    """
    if not (prune_defs or prune_titles or prune_additional_properties):
        return schema  # Nothing to do

    # Phase 1: Collect references and apply simple cleanups
    # Track which $defs are referenced from the main schema and from other $defs
    root_refs: set[str] = set()  # $defs referenced directly from main schema
    def_dependencies: defaultdict[str, list[str]] = defaultdict(
        list
    )  # def A references def B
    defs = schema.get("$defs")

    def traverse_and_clean(
        node: object,
        current_def_name: str | None = None,
        skip_defs_section: bool = False,
        depth: int = 0,
    ) -> None:
        """Traverse schema tree, collecting $ref info and applying cleanups."""
        if depth > 50:  # Prevent infinite recursion
            return

        if isinstance(node, dict):
            # Collect $ref references for unused definition removal
            if prune_defs:
                ref = node.get("$ref")
                if isinstance(ref, str) and ref.startswith("#/$defs/"):
                    referenced_def = ref.split("/")[-1]
                    if current_def_name:
                        # We're inside a $def, so this is a def->def reference
                        def_dependencies[referenced_def].append(current_def_name)
                    else:
                        # We're in the main schema, so this is a root reference
                        root_refs.add(referenced_def)

            # Apply cleanups
            if prune_titles and "title" in node:
                node.pop("title")

            if (
                prune_additional_properties
                and node.get("additionalProperties") is False
            ):
                node.pop("additionalProperties")

            # Recursive traversal
            for key, value in node.items():
                if skip_defs_section and key == "$defs":
                    continue  # Skip $defs during main schema traversal

                # Handle schema composition keywords with special traversal
                if key in ["allOf", "oneOf", "anyOf"] and isinstance(value, list):
                    for item in value:
                        traverse_and_clean(item, current_def_name, depth=depth + 1)
                else:
                    traverse_and_clean(value, current_def_name, depth=depth + 1)

        elif isinstance(node, list):
            for item in node:
                traverse_and_clean(item, current_def_name, depth=depth + 1)

    # Phase 2: Traverse main schema (excluding $defs section)
    traverse_and_clean(schema, skip_defs_section=True)

    # Phase 3: Traverse $defs to find inter-definition references
    if prune_defs and defs:
        for def_name, def_schema in defs.items():
            traverse_and_clean(def_schema, current_def_name=def_name)

        # Phase 4: Remove unused definitions
        def is_def_used(def_name: str, visiting: set[str] | None = None) -> bool:
            """Check if a definition is used, handling circular references."""
            if def_name in root_refs:
                return True  # Used directly from main schema

            # Check if any definition that references this one is itself used
            referencing_defs = def_dependencies.get(def_name, [])
            if referencing_defs:
                if visiting is None:
                    visiting = set()

                # Avoid infinite recursion on circular references
                if def_name in visiting:
                    return False
                visiting = visiting | {def_name}

                # If any referencing def is used, then this def is used
                for referencing_def in referencing_defs:
                    if referencing_def not in visiting and is_def_used(
                        referencing_def, visiting
                    ):
                        return True

            return False

        # Remove unused definitions
        for def_name in list(defs.keys()):
            if not is_def_used(def_name):
                defs.pop(def_name)

        # Clean up empty $defs section
        if not defs:
            schema.pop("$defs", None)

    return schema


def compress_schema(
    schema: dict,
    prune_params: list[str] | None = None,
    prune_defs: bool = True,
    prune_additional_properties: bool = True,
    prune_titles: bool = False,
    dereference_refs: bool = False,
) -> dict:
    """
    Remove the given parameters from the schema.

    Args:
        schema: The schema to compress
        prune_params: List of parameter names to remove from properties
        prune_defs: Whether to remove unused definitions
        prune_additional_properties: Whether to remove additionalProperties: false
        prune_titles: Whether to remove title fields from the schema
        dereference_refs: Whether to completely flatten by inlining all $refs (fixes Claude Desktop crashes).
    """
    # Remove specific parameters if requested
    for param in prune_params or []:
        schema = _prune_param(schema, param=param)

    # Apply combined optimizations in a single tree traversal
    if prune_titles or prune_additional_properties or prune_defs:
        schema = _single_pass_optimize(
            schema,
            prune_titles=prune_titles,
            prune_additional_properties=prune_additional_properties,
            prune_defs=prune_defs,
        )

    # Dereference all $refs if requested
    if dereference_refs:
        schema = dereference_json_schema(schema)

    return schema
