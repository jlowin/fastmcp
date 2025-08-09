# Issue #1372 Status Report

---

## ✅ ISSUE FULLY RESOLVED - Performance Optimized

**Final Solution**: Pre-pruning at parser level + unified ref conversion utility

---

## Overview
GitHub Issue #1372 reports two critical bugs in the experimental OpenAPI parser that cause incorrect JSON Schema generation for MCP tools.

## The Two Core Issues

### Issue 1: Nested $refs in Schema Definitions Not Converted
**Problem**: When schema definitions are copied to `$defs`, internal `$ref` references remain in OpenAPI format (`#/components/schemas/X`) instead of being converted to JSON Schema format (`#/$defs/X`).

**Example**: 
```json
// Schema definition with internal ref (BROKEN)
"$defs": {
  "User": {
    "properties": {
      "profile": {"$ref": "#/components/schemas/Profile"}  // Should be #/$defs/Profile
    }
  }
}
```

### Issue 2: Transitive Dependencies Missing from $defs
**Problem**: Only directly referenced schemas are preserved in `$defs`. Transitive references (A→B→C) get pruned incorrectly.

**Example**: 
- User refs Profile
- Profile refs Address  
- **Address gets removed from `$defs`** (the main bug)

## Root Cause Analysis

The core issue is in the `_replace_ref_with_defs()` function in `schemas.py`. This function has **limited recursion depth** and **doesn't properly handle nested structures** like:

```json
{
  "application/json": {
    "$ref": "#/components/schemas/User"  // This ref is NOT converted
  }
}
```

**Key Finding**: The function converts direct refs (`{"$ref": "..."}`) but fails on nested refs (`{"content": {"$ref": "..."}}`).

## Final Solution Implementation

### Architecture Changes

#### 1. Parser-Level Pre-Pruning (Performance Critical)
The parser now pre-calculates and prunes schema dependencies for each route:
- Added `_extract_schema_dependencies()` - Recursively finds all transitive dependencies
- Added `_extract_route_schema_dependencies()` - Extracts only needed schemas per route
- Modified `parse()` to convert all schemas once at parser level using `_convert_refs_to_defs_format_simple()`
- Each route gets only its required schemas, avoiding 819 schemas × 1018 routes problem

#### 2. Unified Ref Conversion Utility
Created `_ensure_refs_converted()` to replace duplicate conversion logic:
```python
def _ensure_refs_converted(schema: dict[str, Any]) -> dict[str, Any]:
    """Ensure all OpenAPI refs are converted to JSON Schema format."""
    schema_json = msgspec.json.encode(schema).decode("utf-8")
    if "#/components/schemas/" not in schema_json:
        return schema  # Already converted or no refs
    schema_json = schema_json.replace("#/components/schemas/", "#/$defs/")
    return msgspec.json.decode(schema_json.encode("utf-8"))
```

#### 3. Schema Function Optimizations
Modified `_combine_schemas_and_map_params()`:
- Added `convert_refs` flag (default True for backward compatibility)
- Parser passes `convert_refs=False` since it already converted
- Direct calls still get automatic conversion
- Handles both object bodies with properties AND $ref-only request bodies

Modified `extract_output_schema_from_responses()`:
- Uses `_ensure_refs_converted()` for all ref conversions
- Properly includes all transitive dependencies in output schemas

### Performance Impact
- **Before**: 10+ second timeout on GitHub API (819 schemas × 1018 routes)
- **After**: 1.78-3.94 seconds (pre-pruning gives each route ~10-20 schemas)
- **Method**: Pre-pruning at parser level eliminates redundant processing

## Test Results

### All Tests Passing ✅
**6 tests total** in `test_issue_1372.py`:
- ✅ `test_nested_refs_in_schema_definitions_not_converted` - Refs in defs are converted
- ✅ `test_transitive_dependencies_missing_from_response_schemas` - All transitive deps preserved
- ✅ `test_transitive_refs_in_request_body_schemas` - Request body refs handled correctly
- ✅ `test_refs_in_array_items_not_converted` - Array item refs converted
- ✅ `test_refs_in_composition_keywords_not_converted` - oneOf/anyOf/allOf refs converted
- ✅ `test_deeply_nested_transitive_refs_pruned` - Deep transitive chains preserved

### Broader Test Suite
**114 OpenAPI tests** - All passing ✅

## Code Changes Summary

### parser.py Changes
```python
# Added two new methods to OpenAPIParser class:
def _extract_schema_dependencies(self, schema, all_schemas, collected=None):
    """Extract all schema names referenced by a schema (including transitive)."""
    # Recursively finds all $ref references in a schema
    # Handles both #/$defs/ and #/components/schemas/ formats
    # Collects transitive dependencies automatically

def _extract_route_schema_dependencies(self, parameters, request_body, responses, all_schemas):
    """Extract only the schema definitions needed for a specific route."""
    # Checks all parameters, request body, and responses for refs
    # Returns only the schemas actually needed by this route
    # Drastically reduces schema count per route (819 → ~10-20)

# Modified parse() method:
- Converts all schema definitions once at parser level using _convert_refs_to_defs_format_simple()
- Pre-prunes schemas for each route using _extract_route_schema_dependencies()
- Passes convert_refs=False to _combine_schemas_and_map_params() to avoid redundant conversion
```

### schemas.py Changes
```python
# Added unified utility function:
def _ensure_refs_converted(schema: dict[str, Any]) -> dict[str, Any]:
    """Ensure all OpenAPI refs are converted to JSON Schema format."""
    # Fast string replacement using msgspec
    # Only converts if needed (checks first)
    # Returns original if already converted

# Modified _combine_schemas_and_map_params():
- Added convert_refs parameter (default True for backward compatibility)
- Uses _ensure_refs_converted() instead of inline conversion
- Handles $ref-only request bodies (not just object bodies)
- Parser passes convert_refs=False, direct calls use True

# Modified extract_output_schema_from_responses():
- Uses _ensure_refs_converted() for all conversions
- Properly handles transitive dependencies in output schemas
```

### __init__.py Changes
- Removed unnecessary exports of private functions (_ensure_refs_converted, _convert_refs_to_defs_format_simple)

## Files Modified
- `src/fastmcp/experimental/utilities/openapi/schemas.py` - Added _ensure_refs_converted(), modified schema functions
- `src/fastmcp/experimental/utilities/openapi/parser.py` - Added pre-pruning methods, modified parse()
- `src/fastmcp/experimental/utilities/openapi/__init__.py` - Cleaned up exports

## Key Dependencies
- `msgspec` package - Used for fast JSON encoding/decoding (much faster than standard json module)
- Performance tests depend on GitHub API schema download for real-world validation