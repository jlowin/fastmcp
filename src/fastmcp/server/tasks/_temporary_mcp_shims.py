"""
⚠️ TEMPORARY CODE - WORKAROUNDS FOR MCP SDK LIMITATIONS ⚠️

This file contains workarounds for MCP SDK context limitations, specifically for
FastMCPTransport (in-memory transport). These issues don't affect HTTP transports.

Key limitations being worked around:
1. Custom protocol methods (tasks/get, tasks/result) don't receive request context
2. FastMCPTransport runs multiple sessions in-process without proper isolation
3. Docket workers run without access to the FastMCP server instance

These shims will be removed when:
- MCP SDK adds proper context support for custom methods, OR
- We drop FastMCPTransport in favor of HTTP-only, OR
- Docket improves context-passing to workers

DO NOT WRITE TESTS FOR THIS FILE - these are temporary hacks.
"""

import asyncio
from typing import Any, Literal, Union, get_args

from mcp import types as mcp_types
from mcp.types import Request, RequestParams
from pydantic import BaseModel


class TasksGetParams(RequestParams):
    """Parameters for tasks/get request."""

    taskId: str


class TasksGetRequest(Request[TasksGetParams, Literal["tasks/get"]]):
    """Request type for tasks/get method."""

    method: Literal["tasks/get"] = "tasks/get"
    params: TasksGetParams


class TasksResultParams(RequestParams):
    """Parameters for tasks/result request."""

    taskId: str


class TasksResultRequest(Request[TasksResultParams, Literal["tasks/result"]]):
    """Request type for tasks/result method."""

    method: Literal["tasks/result"] = "tasks/result"
    params: TasksResultParams


class TasksDeleteParams(RequestParams):
    """Parameters for tasks/delete request."""

    taskId: str


class TasksDeleteRequest(Request[TasksDeleteParams, Literal["tasks/delete"]]):
    """Request type for tasks/delete method."""

    method: Literal["tasks/delete"] = "tasks/delete"
    params: TasksDeleteParams


class TasksListParams(RequestParams):
    """Parameters for tasks/list request."""

    cursor: str | None = None
    limit: int | None = None


class TasksListRequest(Request[TasksListParams, Literal["tasks/list"]]):
    """Request type for tasks/list method."""

    method: Literal["tasks/list"] = "tasks/list"
    params: TasksListParams


# TODO SEP-1686: Remove these response types when SDK officially supports them
class TasksResponse(BaseModel):
    """Generic response wrapper for task protocol methods.

    SEP-1686 task responses are dicts that can represent CallToolResult,
    GetPromptResult, or ReadResourceResult. This wrapper just passes
    through the raw dict.
    """

    model_config = {"extra": "allow"}

    @classmethod
    def model_validate(cls, obj: Any) -> Any:
        """Parse response dict back into appropriate MCP type.

        The server sends MCP result objects (CallToolResult, GetPromptResult,
        ReadResourceResult) serialized as dicts. We parse them back for the client.
        """
        if not isinstance(obj, dict):
            return obj

        # Try to detect and parse the result type based on structure
        import mcp.types

        # Check for tool result (has 'content' field)
        if "content" in obj:
            try:
                return mcp.types.CallToolResult.model_validate(obj)
            except Exception:
                pass

        # Check for prompt result (has 'messages' field)
        if "messages" in obj:
            try:
                return mcp.types.GetPromptResult.model_validate(obj)
            except Exception:
                pass

        # Check for resource result (has 'contents' field)
        if "contents" in obj:
            try:
                return mcp.types.ReadResourceResult.model_validate(obj)
            except Exception:
                pass

        # Fall back to returning dict as-is
        return obj


# TODO SEP-1686: Remove this monkey-patch when SDK officially supports task methods
# Extend ClientRequest and ServerRequest unions to include SEP-1686 task methods
# This allows both client and server validation to pass

# Patch ClientRequest (used by client to send requests)
client_root_field = mcp_types.ClientRequest.model_fields["root"]
client_original_union = client_root_field.annotation
client_original_types = get_args(client_original_union)

# Build new union (Python 3.10 compatible - can't use Union[*types] syntax)
client_new_union = Union[
    (
        *client_original_types,
        TasksGetRequest,
        TasksResultRequest,
        TasksDeleteRequest,
        TasksListRequest,
    )
]

client_root_field.annotation = client_new_union
mcp_types.ClientRequest.model_rebuild(force=True)

# Patch ServerRequest (used by server to validate incoming requests)
server_root_field = mcp_types.ServerRequest.model_fields["root"]
server_original_union = server_root_field.annotation
server_original_types = get_args(server_original_union)

# Build new union (Python 3.10 compatible - can't use Union[*types] syntax)
server_new_union = Union[
    (
        *server_original_types,
        TasksGetRequest,
        TasksResultRequest,
        TasksDeleteRequest,
        TasksListRequest,
    )
]

server_root_field.annotation = server_new_union
mcp_types.ServerRequest.model_rebuild(force=True)


# HACK: Task ID mapping for FastMCPTransport
# Maps client-provided task IDs → full task keys (with type and component embedded)
# Needed because MCP SDK's custom protocol handlers don't receive session context
_task_id_mapping: dict[str, str] = {}

# HACK: Cancelled task tracking
# Set of task keys that have been cancelled
# Needed because Docket doesn't have a CANCELLED state (SEP-1686 requires it)
_cancelled_tasks: set[str] = set()

_lock = asyncio.Lock()


async def set_state(
    task_key: str,
    state: str,
    keep_alive: int | None = None,
    client_task_id: str | None = None,
) -> None:
    """Set task state and optionally register task ID mapping.

    Registers MCP SDK task ID mapping.

    Args:
        task_key: Full task key (with type and component embedded)
        state: Task state (submitted, working, completed, failed) - unused, for compatibility
        keep_alive: Optional keep_alive (unused, accepted for compatibility)
        client_task_id: Optional client task ID to register in mapping (MCP SDK hack)
    """
    async with _lock:
        if client_task_id:
            _task_id_mapping[client_task_id] = task_key


async def resolve_task_id(client_task_id: str) -> str | None:
    """Resolve client task ID to full task key (HACK for FastMCPTransport).

    TODO: Remove when MCP SDK provides request context to custom protocol methods

    Args:
        client_task_id: Client-provided task ID

    Returns:
        Full task key or None if not found
    """
    async with _lock:
        return _task_id_mapping.get(client_task_id)
