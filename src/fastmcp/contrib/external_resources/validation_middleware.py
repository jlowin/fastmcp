"""Validation middleware for external resource access control."""

from typing import Any

import mcp.types as mt

from fastmcp.exceptions import ToolError
from fastmcp.resources.template import match_uri_template
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)


class ValidationMiddleware(Middleware):
    """Middleware that validates URI parameters against declared external resources.

    By default, validates all tools unless they explicitly set openWorldHint=True.
    This ensures tools can only access external resources that have been explicitly
    declared by the server, providing a controlled gateway to external data.
    """

    def __init__(self, server: Any):
        """Initialize the middleware with a FastMCP server instance.

        Args:
            server: The FastMCP server instance to get resources from
        """
        self.server = server

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool calls to validate URI parameters.

        Only tools with explicit openWorldHint=True bypass validation.
        All other tools (including those without annotations) are validated.
        """
        tool_name = context.message.name
        arguments = context.message.arguments

        # Get the tool from the server
        try:
            tool = await self.server._tool_manager.get_tool(tool_name)
        except Exception:
            # Tool not found - let the normal error handling deal with it
            return await call_next(context)

        # Check if we should skip validation
        # ONLY skip if explicitly openWorldHint=True
        if tool.annotations and tool.annotations.openWorldHint is True:
            logger.debug(
                f"Skipping URI validation for tool '{tool_name}' (openWorldHint=True)"
            )
            return await call_next(context)

        # Validate URI parameters
        logger.debug(f"Validating URIs for tool '{tool_name}'")
        if tool.parameters and isinstance(tool.parameters, dict) and arguments:
            await self._validate_uri_arguments(tool.parameters, arguments, tool_name)

        return await call_next(context)

    async def _validate_uri_arguments(
        self, input_schema: dict[str, Any], arguments: dict[str, Any], tool_name: str
    ) -> None:
        """Validate URI arguments against known resources."""
        properties = input_schema.get("properties", {})
        if not properties:
            return

        # Find URL parameters (those with format: "uri")
        url_params = [
            (name, arguments[name])
            for name, schema in properties.items()
            if name in arguments
            and isinstance(schema, dict)
            and schema.get("format") == "uri"
        ]

        if not url_params:
            return

        # Get resources and templates from server
        resources = await self.server.get_resources()
        templates = await self.server.get_resource_templates()
        resource_uris = {str(r.uri) for r in resources.values()}

        # Validate each URL parameter
        for param_name, uri_value in url_params:
            uri_str = str(uri_value)

            # Skip if matches exact resource or template
            if uri_str in resource_uris or any(
                match_uri_template(uri_str, t.uri_template) is not None
                for t in templates.values()
            ):
                continue

            raise ToolError(
                f"Unknown resource URI '{uri_str}' for parameter '{param_name}' in tool '{tool_name}'. "
                f"This tool requires valid resource URIs. To allow any URI, set openWorldHint=True."
            )
