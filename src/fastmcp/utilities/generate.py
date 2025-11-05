"""Code generation utilities for MCP tools.

This module provides functions to generate standalone Python scripts from MCP tool
definitions, enabling progressive discovery and context-efficient agent workflows.
"""

from datetime import datetime, timezone

import mcp.types


def to_snake_case(name: str) -> str:
    """Convert a tool name to snake_case for use as a Python identifier.

    Args:
        name: Tool name (e.g., "get-document", "getTabs", "list.items")

    Returns:
        Snake case identifier (e.g., "get_document", "get_tabs", "list_items")
    """
    # Replace common separators with underscores
    result = name.replace("-", "_").replace(".", "_").replace(" ", "_")
    # Handle camelCase by inserting underscores before capitals
    import re

    result = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", result)
    return result.lower()


def json_schema_to_python_type(prop: dict) -> str:
    """Convert JSON schema property to Python type hint.

    Args:
        prop: JSON schema property definition

    Returns:
        Python type hint string (e.g., "str", "int", "list", "dict")
    """
    json_type = prop.get("type", "any")

    type_map = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict",
    }

    return type_map.get(json_type, "Any")


def generate_typed_params(input_schema: dict) -> tuple[str, list[str]]:
    """Generate function parameters and parameter names from JSON schema.

    Args:
        input_schema: JSON schema for tool input parameters

    Returns:
        Tuple of (params_str, param_names) where:
        - params_str: Formatted function parameters (e.g., "name: str, age: int | None = None")
        - param_names: List of parameter names for building the args dict
    """
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    params = []
    param_names = []

    for name, prop in properties.items():
        param_names.append(name)
        python_type = json_schema_to_python_type(prop)

        if name in required:
            params.append(f"{name}: {python_type}")
        else:
            params.append(f"{name}: {python_type} | None = None")

    return ", ".join(params), param_names


def generate_args_dict(param_names: list[str], indent: str = "            ") -> str:
    """Generate the arguments dictionary for tool calling.

    Args:
        param_names: List of parameter names
        indent: Indentation string for formatting

    Returns:
        Formatted dictionary string for passing to call_tool
    """
    if not param_names:
        return "{}"

    lines = ["{"]
    for name in param_names:
        lines.append(f'{indent}"{name}": {name},')
    lines.append(f"{indent[:-4]}}}")
    return "\n".join(lines)


def generate_auth_code(
    auth_mode: str, auth_value: str | None, server_url: str
) -> tuple[str, str]:
    """Generate authentication code for the tool script.

    Args:
        auth_mode: Authentication mode ("none", "oauth", "env_var", "token")
        auth_value: Auth value (env var name for env_var mode, token for token mode)
        server_url: URL of the MCP server (for OAuth)

    Returns:
        Tuple of (imports, get_auth_function) where:
        - imports: Import statements needed for auth
        - get_auth_function: Complete get_auth() function implementation
    """
    if auth_mode == "oauth":
        imports = "from fastmcp.client.auth import OAuth"
        get_auth = f'''def get_auth():
    """Get authentication for the MCP server."""
    return OAuth(mcp_url="{server_url}")'''

    elif auth_mode == "env_var":
        imports = ""
        get_auth = f'''def get_auth():
    """Get authentication for the MCP server."""
    token = os.environ.get("{auth_value}")
    if not token:
        raise ValueError("Missing required environment variable: {auth_value}")
    return token'''

    elif auth_mode == "token":
        imports = ""
        get_auth = f'''def get_auth():
    """Get authentication for the MCP server."""
    return "{auth_value}"'''

    else:  # none
        imports = ""
        get_auth = '''def get_auth():
    """Get authentication for the MCP server."""
    return None'''

    return imports, get_auth


def generate_tool_script(
    tool: mcp.types.Tool,
    server_url: str,
    auth_mode: str = "none",
    auth_value: str | None = None,
) -> str:
    """Generate a standalone Python script for an MCP tool.

    Args:
        tool: MCP tool definition
        server_url: URL of the MCP server
        auth_mode: Authentication mode ("none", "oauth", "env_var", "token")
        auth_value: Auth value (env var name for env_var mode, token for token mode)

    Returns:
        Complete Python script as a string
    """
    function_name = to_snake_case(tool.name)

    # Generate typed parameters
    params_str, param_names = generate_typed_params(tool.inputSchema)
    if not params_str:
        params_str = ""  # No parameters

    # Generate args dict
    args_dict = generate_args_dict(param_names)

    # Generate auth code
    auth_imports, auth_function = generate_auth_code(auth_mode, auth_value, server_url)

    imports = """import asyncio
import json
import os
import sys
from typing import Any

from fastmcp import Client"""
    if auth_imports:
        imports += f"\n{auth_imports}"

    return f'''\
# /// script
# dependencies = ["fastmcp>=2.0.0"]
# ///

"""{tool.name}

{tool.description or ""}
"""

{imports}

SERVER_URL = "{server_url}"


{auth_function}


async def {function_name}({params_str}) -> Any:
    """{tool.description or tool.name}"""
    async with Client(SERVER_URL, auth=get_auth()) as client:
        result = await client.call_tool("{tool.name}", {args_dict})
        return result.data if result.data else result.content


if __name__ == "__main__":
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {{}}
    result = asyncio.run({function_name}(**params))
    print(json.dumps(result, indent=2) if not isinstance(result, str) else result)
'''


def generate_agents_md(
    server_name: str,
    server_url: str,
    tools: list[mcp.types.Tool],
    auth_mode: str = "none",
    auth_value: str | None = None,
    instructions: str | None = None,
) -> str:
    """Generate AGENTS.md documentation for agent usage.

    Args:
        server_name: Name of the MCP server
        server_url: URL of the MCP server
        tools: List of MCP tools
        auth_mode: Authentication mode ("none", "oauth", "env_var", "token")
        auth_value: Auth value (env var name for env_var mode, token for token mode)
        instructions: Optional server-provided instructions for using the tools

    Returns:
        Markdown documentation string
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build instructions section if provided
    instructions_section = ""
    if instructions:
        instructions_section = f"""
## Server Instructions

{instructions}
"""

    # Generate tool list
    tool_lines = []
    for tool in tools:
        filename = to_snake_case(tool.name) + ".py"
        description = tool.description or tool.name
        tool_lines.append(f"- `{filename}` - {description}")

    tools_list = "\n".join(tool_lines)

    return f"""\
# MCP Tools: {server_name}

Generated from: {server_url}
Generated at: {timestamp}
Tools: {len(tools)}
{instructions_section}
## Quick Start

```bash
# Each script accepts JSON parameters
uv run tool_name.py '{{"param1":"value1","param2":"value2"}}'

# No parameters (empty object)
uv run tool_name.py '{{}}'

# Or omit for empty params
uv run tool_name.py
```

## Available Tools

{tools_list}

## Usage

Each script is standalone and can be:
- **Run directly**: `uv run tool_name.py '{{"param":"value"}}'` (dependencies auto-installed)
- **Imported**: `from tool_name import tool_name`
- **Modified or deleted** without affecting other scripts

**Parameters:** All scripts accept JSON as first argument. Pass an empty object `{{}}` or omit for tools with no parameters.

**Dependencies:** Scripts use PEP 723 inline metadata, so `uv` automatically installs dependencies.

## Examples

```bash
# Simple string parameter
uv run greet.py '{{"name":"Alice"}}'

# Multiple parameters
uv run greet.py '{{"name":"Alice","title":"Dr"}}'

# Complex nested objects
uv run create_user.py '{{"profile":{{"name":"Alice","age":30}},"tags":["admin","user"]}}'

# No parameters
uv run get_status.py
```
"""
