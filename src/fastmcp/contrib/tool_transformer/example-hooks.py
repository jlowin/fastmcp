"""Sample code for FastMCP using InterceptingProxyTool."""

import asyncio
from typing import Any

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.tool_transformer.tool_transformer import proxy_tool
from fastmcp.exceptions import ToolError

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
    async with Client(third_party_mcp_config) as remote_mcp_client:
        proxied_mcp_server = FastMCP.as_proxy(remote_mcp_client)

        proxied_tools = await proxied_mcp_server.get_tools()

        frontend_server = FastMCP("Frontend Server")

        async def pre_call_hook(
            tool_args: dict[str, Any],
            hook_args: dict[str, Any],
        ) -> None:
            if tool_args.get("source_timezone") == "America/New_York":
                raise ToolError("New Yorkers are not allowed to use this tool.")

        proxy_tool(
            proxied_tools["convert_time"],
            frontend_server,
            name="transformed_convert_time",
            description="Converts a time from New York to another timezone.",
            pre_call_hook=pre_call_hook,
        )

        await frontend_server.run_async(transport="sse")


def run_mcp():
    asyncio.run(async_main())


if __name__ == "__main__":
    run_mcp()
