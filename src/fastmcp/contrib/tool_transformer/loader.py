import json
from pathlib import Path
from typing import Any

import yaml

from fastmcp.client.client import Client
from fastmcp.contrib.tool_transformer.models import ToolOverride
from fastmcp.contrib.tool_transformer.tool_transformer import proxy_tool
from fastmcp.server.server import FastMCP
from fastmcp.utilities.mcp_config import MCPConfig


def overrides_from_dict(obj: dict[str, Any]) -> dict[str, ToolOverride]:
    return {
        tool_name: ToolOverride.model_validate(tool_override)
        for tool_name, tool_override in obj.items()
    }


def overrides_from_yaml(yaml_str: str) -> dict[str, ToolOverride]:
    return overrides_from_dict(yaml.safe_load(yaml_str))


def overrides_from_yaml_file(yaml_file: Path) -> dict[str, ToolOverride]:
    with Path(yaml_file).open(encoding="utf-8") as f:
        return overrides_from_yaml(yaml_str=f.read())


def overrides_from_json(json_str: str) -> dict[str, ToolOverride]:
    return overrides_from_dict(json.loads(json_str))


def overrides_from_json_file(json_file: Path) -> dict[str, ToolOverride]:
    with Path(json_file).open(encoding="utf-8") as f:
        return overrides_from_json(f.read())


async def proxy_mcp_server_with_overrides(
    config: MCPConfig,
    tool_override: ToolOverride,
    client_kwargs: dict[str, Any] = {},
    server_kwargs: dict[str, Any] = {},
) -> FastMCP:
    """Run a MCP server with overrides."""

    client = Client(config, **client_kwargs)

    server = FastMCP.as_proxy(client, **server_kwargs)

    server_tools = await server.get_tools()

    for tool in server_tools.values():
        proxy_tool(tool, server, override=tool_override)

    return server
