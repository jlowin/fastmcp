"""Sample code for FastMCP using InterceptingProxyTool."""

import asyncio
from pathlib import Path

import yaml

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.tool_transformer import proxy_tool
from fastmcp.contrib.tool_transformer.loader import overrides_from_yaml_file

third_party_mcp_config = {
    "time": {
        "command": "uvx",
        "args": [
            "git+https://github.com/modelcontextprotocol/servers.git@2025.4.24#subdirectory=src/time",
            "--local-timezone=America/New_York",
        ],
    }
}

override_config_yaml = yaml.safe_load("""
tools:
- convert_time:
    description: >-
        An updated multi-line description 
        for the time tool.
    parameter_overrides:
        source_timezone:
        description: This field now has a description and a constant value
        constant: America/New_York
        time:
        description: This field now has a description and a default value
        default: "3:00"
""")


async def async_main():
    async with Client(third_party_mcp_config) as remote_mcp_client:
        backend_server = FastMCP.as_proxy(remote_mcp_client)

        backend_tools = await backend_server.get_tools()

        frontend_server = FastMCP("Frontend Server")

        tool_overrides = overrides_from_yaml_file(Path("override_config.yaml"))

        proxy_tool(
            tool=backend_tools["convert_time"],
            server=frontend_server,
            override=tool_overrides["convert_time"],
        )

        await frontend_server.run_async(transport="sse")


def run_mcp():
    asyncio.run(async_main())


if __name__ == "__main__":
    run_mcp()
