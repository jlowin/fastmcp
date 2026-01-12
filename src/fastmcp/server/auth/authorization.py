"""Authorization checks for FastMCP tools.

This module provides callable-based authorization for tools. Auth checks
are functions that receive an AuthContext and return True to allow access
or False to deny.

Auth checks can also raise exceptions:
- AuthorizationError: Propagates with the custom message for explicit denial
- Other exceptions: Masked for security (logged, treated as auth failure)

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server.auth import require_auth, require_scopes

    mcp = FastMCP()

    @mcp.tool(auth=require_auth)
    def protected_tool(): ...

    @mcp.tool(auth=require_scopes("admin"))
    def admin_tool(): ...

    @mcp.tool(auth=[require_auth, require_scopes("write")])
    def write_tool(): ...
    ```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, cast

from fastmcp.exceptions import AuthorizationError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp.server.auth import AccessToken
    from fastmcp.tools.tool import Tool


@dataclass
class AuthContext:
    """Context passed to auth check callables.

    This object is passed to each auth check function and provides
    access to the current authentication token and the tool being accessed.

    Attributes:
        token: The current access token, or None if unauthenticated.
        tool: The tool being accessed.
    """

    token: AccessToken | None
    tool: Tool


# Type alias for auth check functions
AuthCheck = Callable[[AuthContext], bool]


def require_auth(ctx: AuthContext) -> bool:
    """Require any valid authentication.

    Returns True if the request has a valid token, False otherwise.

    Example:
        ```python
        @mcp.tool(auth=require_auth)
        def protected_tool(): ...
        ```
    """
    return ctx.token is not None


def require_scopes(*scopes: str) -> AuthCheck:
    """Require specific OAuth scopes.

    Returns an auth check that requires ALL specified scopes to be present
    in the token (AND logic).

    Args:
        *scopes: One or more scope strings that must all be present.

    Example:
        ```python
        @mcp.tool(auth=require_scopes("admin"))
        def admin_tool(): ...

        @mcp.tool(auth=require_scopes("read", "write"))
        def read_write_tool(): ...
        ```
    """
    required = set(scopes)

    def check(ctx: AuthContext) -> bool:
        if ctx.token is None:
            return False
        return required.issubset(set(ctx.token.scopes))

    return check


def restrict_tag(tag: str, *, scopes: list[str]) -> AuthCheck:
    """Restrict tools with a specific tag to require certain scopes.

    If the tool has the specified tag, the token must have ALL the
    required scopes. If the tool doesn't have the tag, access is allowed.

    Args:
        tag: The tag that triggers the scope requirement.
        scopes: List of scopes required when the tag is present.

    Example:
        ```python
        # Tools tagged "admin" require the "admin" scope
        AuthMiddleware(auth=restrict_tag("admin", scopes=["admin"]))
        ```
    """
    required = set(scopes)

    def check(ctx: AuthContext) -> bool:
        if tag not in ctx.tool.tags:
            return True  # Tag not present, no restriction
        if ctx.token is None:
            return False
        return required.issubset(set(ctx.token.scopes))

    return check


def run_auth_checks(
    checks: AuthCheck | list[AuthCheck],
    ctx: AuthContext,
) -> bool:
    """Run auth checks with AND logic.

    All checks must pass for authorization to succeed.

    Auth checks can:
    - Return True to allow access
    - Return False to deny access
    - Raise AuthorizationError to deny with a custom message (propagates)
    - Raise other exceptions (masked for security, treated as denial)

    Args:
        checks: A single check function or list of check functions.
        ctx: The auth context to pass to each check.

    Returns:
        True if all checks pass, False if any check fails.

    Raises:
        AuthorizationError: If an auth check explicitly raises it.
    """
    check_list = [checks] if not isinstance(checks, list) else checks
    check_list = cast(list[AuthCheck], check_list)

    for check in check_list:
        try:
            if not check(ctx):
                return False
        except AuthorizationError:
            # Let AuthorizationError propagate with its custom message
            raise
        except Exception:
            # Mask other exceptions for security - log and treat as auth failure
            logger.warning(
                f"Auth check {getattr(check, '__name__', repr(check))} "
                "raised an unexpected exception",
                exc_info=True,
            )
            return False

    return True
