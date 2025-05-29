"""Sample code for FastMCP using InterceptingProxyTool."""

import asyncio

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.tool_transformer.models import ToolParameter
from fastmcp.contrib.tool_transformer.tool_transformer import (
    proxy_tool,
)

third_party_mcp_config = {
    "time": {
        "command": "uvx",
        "args": [
            "git+https://github.com/modelcontextprotocol/servers.git@2025.4.24#subdirectory=src/time",
            "--local-timezone=America/New_York",
        ],
    }
}


async def async_main():
    async with Client(third_party_mcp_config, timeout=30) as remote_mcp_client:
        proxied_mcp_server = FastMCP.as_proxy(remote_mcp_client)

        proxied_tools = await proxied_mcp_server.get_tools()

        frontend_server = FastMCP("Frontend Server")

        proxy_tool(
            proxied_tools["convert_time"],
            server=frontend_server,
            name="transformed_convert_time",
            description="Converts a time from New York to another timezone.",
            parameter_overrides=[
                ToolParameter[str](
                    name="source_timezone",
                    description="The timezone of the time to convert.",
                    constant="America/New_York",  # Source Timezone is now required to be America/New_York
                ),
                ToolParameter[str](
                    name="time",
                    description="The time to convert. Must be in the format HH:MM. Default is 3:00.",
                    default="3:00",  # Time now defaults to 3:00
                ),
                # No override of the override the target_timezone parameter
            ],
        )

        await frontend_server.run_async(transport="sse")


def run_mcp():
    asyncio.run(async_main())


if __name__ == "__main__":
    run_mcp()
