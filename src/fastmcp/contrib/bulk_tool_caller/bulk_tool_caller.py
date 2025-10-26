import warnings
from typing import Any

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import FastMCPTransport
from fastmcp.contrib.mcp_mixin.mcp_mixin import (
    _DEFAULT_SEPARATOR_TOOL,
    MCPMixin,
    mcp_tool,
)

# Re-export types from the new location for backward compatibility
from fastmcp.server.middleware.bulk_tool_caller_types import (
    CallToolRequest,
    CallToolRequestResult,
)


class BulkToolCaller(MCPMixin):
    """A class to provide a "bulk tool call" tool for a FastMCP server.

    .. deprecated:: 2.1.0
        Use :class:`~fastmcp.server.middleware.BulkToolCallerMiddleware` instead.
        This class is maintained for backward compatibility but will be removed
        in a future version.

        Old usage::

            bulk_tool_caller = BulkToolCaller()
            bulk_tool_caller.register_tools(mcp)

        New usage::

            from fastmcp.server.middleware import BulkToolCallerMiddleware
            mcp = FastMCP(middleware=[BulkToolCallerMiddleware()])
    """

    def register_tools(
        self,
        mcp_server: "FastMCP",
        prefix: str | None = None,
        separator: str = _DEFAULT_SEPARATOR_TOOL,
    ) -> None:
        """Register the tools provided by this class with the given MCP server.

        .. deprecated:: 2.1.0
            Use :class:`~fastmcp.server.middleware.BulkToolCallerMiddleware` instead.
        """
        warnings.warn(
            "BulkToolCaller is deprecated and will be removed in a future version. "
            "Use BulkToolCallerMiddleware instead: "
            "FastMCP(middleware=[BulkToolCallerMiddleware()])",
            DeprecationWarning,
            stacklevel=2,
        )

        self.connection = FastMCPTransport(mcp_server)

        super().register_tools(mcp_server=mcp_server)

    @mcp_tool()
    async def call_tools_bulk(
        self, tool_calls: list[CallToolRequest], continue_on_error: bool = True
    ) -> list[CallToolRequestResult]:
        """
        Call multiple tools registered on this MCP server in a single request. Each call can
         be for a different tool and can include different arguments. Useful for speeding up
         what would otherwise take several individual tool calls.
        """
        results = []

        for tool_call in tool_calls:
            result = await self._call_tool(tool_call.tool, tool_call.arguments)

            results.append(result)

            if result.isError and not continue_on_error:
                return results

        return results

    @mcp_tool()
    async def call_tool_bulk(
        self,
        tool: str,
        tool_arguments: list[dict[str, str | int | float | bool | None]],
        continue_on_error: bool = True,
    ) -> list[CallToolRequestResult]:
        """
        Call a single tool registered on this MCP server multiple times with a single request.
         Each call can include different arguments. Useful for speeding up what would otherwise
         take several individual tool calls.

        Args:
            tool: The name of the tool to call.
            tool_arguments: A list of dictionaries, where each dictionary contains the arguments for an individual run of the tool.
        """
        results = []

        for tool_call_arguments in tool_arguments:
            result = await self._call_tool(tool, tool_call_arguments)

            results.append(result)

            if result.isError and not continue_on_error:
                return results

        return results

    async def _call_tool(
        self, tool: str, arguments: dict[str, Any]
    ) -> CallToolRequestResult:
        """
        Helper method to call a tool with the provided arguments.
        """

        async with Client(self.connection) as client:
            result = await client.call_tool_mcp(name=tool, arguments=arguments)

            return CallToolRequestResult(
                tool=tool,
                arguments=arguments,
                isError=result.isError,
                content=result.content,
            )
