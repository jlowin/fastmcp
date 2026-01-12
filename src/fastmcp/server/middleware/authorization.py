"""Authorization middleware for FastMCP.

This module provides middleware-based authorization using callable auth checks.
AuthMiddleware applies auth checks globally to all tools on the server.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.auth import require_auth, require_scopes, restrict_tag
    from fastmcp.server.middleware import AuthMiddleware

    # Require auth for all tools
    mcp = FastMCP(middleware=[
        AuthMiddleware(auth=require_auth)
    ])

    # Tag-based: tools tagged "admin" require "admin" scope
    mcp = FastMCP(middleware=[
        AuthMiddleware(auth=restrict_tag("admin", scopes=["admin"]))
    ])
    ```
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import mcp.types as mt

from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth.authorization import (
    AuthCheck,
    AuthContext,
    run_auth_checks,
)
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware.middleware import (
    CallNext,
    Middleware,
    MiddlewareContext,
)
from fastmcp.tools.tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class AuthMiddleware(Middleware):
    """Global authorization middleware using callable checks.

    This middleware applies auth checks to all tools on the server.
    It uses the same callable API as tool-level auth checks.

    The middleware:
    - Filters tools from list_tools response based on auth checks
    - Checks auth before tool execution in call_tool

    Args:
        auth: A single auth check function or list of check functions.
            All checks must pass for authorization to succeed (AND logic).

    Example:
        ```python
        from fastmcp import FastMCP
        from fastmcp.server.auth import require_auth, require_scopes

        # Require any authentication for all tools
        mcp = FastMCP(middleware=[AuthMiddleware(auth=require_auth)])

        # Require specific scope for all tools
        mcp = FastMCP(middleware=[AuthMiddleware(auth=require_scopes("api"))])

        # Combined checks (AND logic)
        mcp = FastMCP(middleware=[
            AuthMiddleware(auth=[require_auth, require_scopes("api")])
        ])
        ```
    """

    def __init__(self, auth: AuthCheck | list[AuthCheck]) -> None:
        self.auth = auth

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        """Filter tools/list response based on auth checks."""
        tools = await call_next(context)

        # STDIO has no auth concept, skip filtering
        # Late import to avoid circular import with context.py
        from fastmcp.server.context import _current_transport

        if _current_transport.get() == "stdio":
            return tools

        token = get_access_token()

        authorized_tools: list[Tool] = []
        for tool in tools:
            ctx = AuthContext(token=token, tool=tool)
            if run_auth_checks(self.auth, ctx):
                authorized_tools.append(tool)

        return authorized_tools

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Check auth before tool execution."""
        # STDIO has no auth concept, skip enforcement
        # Late import to avoid circular import with context.py
        from fastmcp.server.context import _current_transport

        if _current_transport.get() == "stdio":
            return await call_next(context)

        # Get the tool being called
        tool_name = context.message.name
        fastmcp = context.fastmcp_context
        if fastmcp is None:
            # Fail closed: deny access when context is missing
            logger.warning(
                f"AuthMiddleware: fastmcp_context is None for tool '{tool_name}'. "
                "Denying access for security."
            )
            raise AuthorizationError(
                f"Authorization failed for tool '{tool_name}': missing context"
            )

        tool = await fastmcp.fastmcp.get_tool(tool_name)

        token = get_access_token()
        ctx = AuthContext(token=token, tool=tool)

        if not run_auth_checks(self.auth, ctx):
            raise AuthorizationError(
                f"Authorization failed for tool '{tool_name}': insufficient permissions"
            )

        return await call_next(context)
