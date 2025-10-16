import asyncio
import json
from typing import Any

import yaml

from fastmcp import FastMCP


# Define custom serializers
def yaml_serializer(data: Any) -> str:
    """Serialize data as YAML."""
    return yaml.dump(data, width=100, sort_keys=False)


def json_pretty_serializer(data: Any) -> str:
    """Serialize data as pretty-printed JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False)


# Create server with default YAML serializer
server = FastMCP(name="CustomSerializerExample", tool_serializer=yaml_serializer)


@server.tool
def get_config() -> dict:
    """Returns configuration data (uses default YAML serializer)."""
    return {"database": "postgres", "port": 5432, "ssl": True}


@server.tool(serializer=json_pretty_serializer)
def get_metrics() -> dict:
    """Returns metrics data (uses custom JSON pretty serializer)."""
    return {"cpu": 45.2, "memory": 78.1, "disk": 62.5}


@server.tool
def get_status() -> dict:
    """Returns status information (uses default YAML serializer)."""
    return {"status": "running", "uptime": 3600, "healthy": True}


async def example_usage():
    print("=== Tool with default YAML serializer ===")
    result1 = await server._call_tool_mcp("get_config", {})
    print(result1[0][0].text)  # type: ignore[attr-defined]
    print()

    print("=== Tool with custom JSON pretty serializer ===")
    result2 = await server._call_tool_mcp("get_metrics", {})
    print(result2[0][0].text)  # type: ignore[attr-defined]
    print()

    print("=== Another tool with default YAML serializer ===")
    result3 = await server._call_tool_mcp("get_status", {})
    print(result3[0][0].text)  # type: ignore[attr-defined]
    print()

    print("This example demonstrates:")
    print("1. Server-level default serializer (YAML)")
    print("2. Per-tool custom serializer (JSON pretty)")
    print("3. Multiple tools can use different serializers")


if __name__ == "__main__":
    asyncio.run(example_usage())
    server.run()
