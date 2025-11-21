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

═══════════════════════════════════════════════════════════════════════════════
SDK TYPE RECONCILIATION (SEP-1686 Phase 3)
═══════════════════════════════════════════════════════════════════════════════

Type names below match MCP SDK draft implementation (feat/tasks branch) WHERE
the SDK has defined types. However, SDK draft types contain ERRORS vs final spec:

❌ SDK DIVERGENCES FROM FINAL SPEC (we correct these):
   1. SDK uses `keepAlive` field - WRONG, spec requires `ttl` (line 430-432)
   2. SDK MISSING `createdAt` field - WRONG, spec REQUIRES it (line 430)
   3. SDK allows "submitted" initial status - WRONG, spec requires "working" (line 381)

✅ OUR CORRECTIONS (spec-compliant):
   - We use `ttl` field (not keepAlive)
   - We include required `createdAt` timestamp
   - We use "working" as initial task status
   - We define CancelTaskRequest (SDK doesn't have it yet)

These shim types will be easy to replace when SDK is updated to match final spec.

SDK Reference: /home/chris/src/github.com/modelcontextprotocol/python-sdk
               src/mcp/types.py lines 46-717 (feat/tasks branch)
Spec Reference: SEP-1686 final specification
"""

from typing import Any, Literal, Union, get_args

from mcp import types as mcp_types
from mcp.types import (
    PaginatedRequest,
    PaginatedRequestParams,
    Request,
    RequestParams,
    Result,
)
from pydantic import BaseModel, ConfigDict

# ═══════════════════════════════════════════════════════════════════════════
# tasks/get - Get task status
# SDK has: GetTaskRequest / GetTaskParams / GetTaskResult (types.py:631-665)
# ═══════════════════════════════════════════════════════════════════════════


class GetTaskParams(RequestParams):
    """Parameters for tasks/get request.

    SDK-compatible naming (was TasksGetParams).
    """

    taskId: str
    """The task identifier."""

    model_config = ConfigDict(extra="allow")


class GetTaskRequest(Request[GetTaskParams, Literal["tasks/get"]]):
    """Request type for tasks/get method.

    SDK-compatible naming (was TasksGetRequest).
    SDK reference: types.py:640-644
    """

    method: Literal["tasks/get"] = "tasks/get"
    params: GetTaskParams


class GetTaskResult(Result):
    """Response to a tasks/get request.

    SDK-compatible naming. Matches SDK structure but with spec-compliant fields.
    SDK reference: types.py:647-665

    ⚠️ SPEC CORRECTIONS (SDK is wrong):
    - We use `ttl` field (SDK incorrectly uses `keepAlive`)
    - We include `createdAt` field (SDK is missing this REQUIRED field per spec line 430)
    """

    taskId: str
    """The unique identifier for this task."""

    status: Literal[
        "working",
        "input_required",
        "completed",
        "failed",
        "cancelled",
    ]
    """Current task status."""

    createdAt: str
    """ISO 8601 timestamp when task was created. REQUIRED per spec line 430.
    ⚠️ SDK is missing this field entirely!"""

    ttl: int | None = None
    """Time in milliseconds to keep task results available after completion.
    ⚠️ SDK incorrectly calls this `keepAlive` - spec requires `ttl` (line 430-432)"""

    pollInterval: int | None = None
    """Recommended polling frequency in milliseconds."""

    statusMessage: str | None = None
    """Optional human-readable message describing the current state. Per spec line 403."""

    model_config = ConfigDict(extra="allow")


# ═══════════════════════════════════════════════════════════════════════════
# tasks/result - Get task result payload
# SDK has: GetTaskPayloadRequest / GetTaskPayloadParams (types.py:668-681)
# ═══════════════════════════════════════════════════════════════════════════


class GetTaskPayloadParams(RequestParams):
    """Parameters for tasks/result request.

    SDK-compatible naming (was TasksResultParams).
    """

    taskId: str
    """The task identifier."""

    model_config = ConfigDict(extra="allow")


class GetTaskPayloadRequest(Request[GetTaskPayloadParams, Literal["tasks/result"]]):
    """Request type for tasks/result method.

    SDK-compatible naming (was TasksResultRequest).
    SDK reference: types.py:677-681
    """

    method: Literal["tasks/result"] = "tasks/result"
    params: GetTaskPayloadParams


# ═══════════════════════════════════════════════════════════════════════════
# tasks/list - List tasks
# SDK has: ListTasksRequest / ListTasksResult (types.py:684-700)
# ═══════════════════════════════════════════════════════════════════════════


class ListTasksRequest(PaginatedRequest[Literal["tasks/list"]]):
    """Request type for tasks/list method.

    SDK-compatible naming (was TasksListRequest).
    SDK reference: types.py:684-688
    """

    method: Literal["tasks/list"] = "tasks/list"
    params: PaginatedRequestParams | None = None


class ListTasksResult(Result):
    """Response to a tasks/list request.

    SDK-compatible naming.
    SDK reference: types.py:691-700
    """

    tasks: list[dict[str, Any]]
    """List of tasks (Task objects)."""

    nextCursor: str | None = None
    """Opaque token for pagination."""

    model_config = ConfigDict(extra="allow")


# ═══════════════════════════════════════════════════════════════════════════
# tasks/cancel - Cancel a task
# SDK DOES NOT HAVE THIS YET - This is our extension per final spec
# ═══════════════════════════════════════════════════════════════════════════


class CancelTaskParams(RequestParams):
    """Parameters for tasks/cancel request.

    ⚠️ SDK doesn't define CancelTaskRequest yet - this is our spec-compliant extension.
    Follows SDK naming pattern (was TasksCancelParams).
    """

    taskId: str
    """The task identifier."""

    model_config = ConfigDict(extra="allow")


class CancelTaskRequest(Request[CancelTaskParams, Literal["tasks/cancel"]]):
    """Request type for tasks/cancel method.

    ⚠️ SDK doesn't define CancelTaskRequest yet - this is our spec-compliant extension.
    Follows SDK naming pattern (was TasksCancelRequest).
    Spec reference: SEP-1686 lines 254-276
    """

    method: Literal["tasks/cancel"] = "tasks/cancel"
    params: CancelTaskParams


# ═══════════════════════════════════════════════════════════════════════════
# notifications/tasks/status - Task status change notification
# SDK DOES NOT HAVE THIS YET - This is our extension per final spec lines 436-444
# ═══════════════════════════════════════════════════════════════════════════


class TaskStatusNotificationParams(BaseModel):
    """Parameters for notifications/tasks/status.

    Per SEP-1686 lines 436-444, servers MAY send status notifications.
    Params contain full Task object (lines 452-454).
    """

    taskId: str
    """The unique identifier for this task."""

    status: Literal[
        "working",
        "input_required",
        "completed",
        "failed",
        "cancelled",
    ]
    """Current task status."""

    createdAt: str
    """ISO 8601 timestamp when task was created."""

    ttl: int | None = None
    """Time in milliseconds to keep task results available after completion."""

    pollInterval: int | None = None
    """Recommended polling frequency in milliseconds."""

    statusMessage: str | None = None
    """Optional human-readable message describing the current state."""

    model_config = ConfigDict(extra="allow")


class TaskStatusNotification(
    mcp_types.Notification[
        TaskStatusNotificationParams, Literal["notifications/tasks/status"]
    ]  # type: ignore[type-arg]
):
    """Notification for task status changes.

    Per SEP-1686 lines 436-444, servers MAY send these notifications when
    task state changes. This is an optional optimization that reduces client
    polling frequency.
    """

    method: Literal["notifications/tasks/status"] = "notifications/tasks/status"
    params: TaskStatusNotificationParams


# ═══════════════════════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════════════════════
# Extend SDK Param Types to Add `task` Field (SEP-1686 Phase 2.1)
# ═══════════════════════════════════════════════════════════════════════════

# Per SEP-1686 final spec, task metadata should be a direct param field,
# NOT nested in _meta. The SDK draft incorrectly uses _meta approach.
#
# We extend SDK param types to add the spec-compliant task field, then
# monkeypatch them back into the SDK module so ALL SDK code uses our versions.
#
# When SDK is fixed to match final spec, we can simply remove this monkeypatch.


class CallToolRequestParams(mcp_types.CallToolRequestParams):
    """Extended CallToolRequestParams with task field per SEP-1686 final spec.

    SDK draft uses _meta approach (WRONG per final spec lines 143-148).
    Final spec requires task as direct sibling to name/arguments.

    This extension adds the spec-compliant task field.
    """

    task: dict[str, Any] | None = None
    """Task metadata per SEP-1686 final spec. Contains ttl field.
    Example: {"ttl": 60000}"""


class GetPromptRequestParams(mcp_types.GetPromptRequestParams):
    """Extended GetPromptRequestParams with task field per SEP-1686 final spec.

    SDK draft uses _meta approach (WRONG per final spec).
    This extension adds the spec-compliant task field.
    """

    task: dict[str, Any] | None = None
    """Task metadata per SEP-1686 final spec. Contains ttl field."""


class ReadResourceRequestParams(mcp_types.ReadResourceRequestParams):
    """Extended ReadResourceRequestParams with task field per SEP-1686 final spec.

    SDK draft uses _meta approach (WRONG per final spec).
    This extension adds the spec-compliant task field.
    """

    task: dict[str, Any] | None = None
    """Task metadata per SEP-1686 final spec. Contains ttl field."""


# Monkeypatch SDK to use our extended param types everywhere
# This makes ALL SDK code (client sessions, server handlers, etc.) automatically
# use our spec-compliant param types with the task field.
mcp_types.CallToolRequestParams = CallToolRequestParams  # type: ignore[misc]
mcp_types.GetPromptRequestParams = GetPromptRequestParams  # type: ignore[misc]
mcp_types.ReadResourceRequestParams = ReadResourceRequestParams  # type: ignore[misc]

# Force Pydantic to rebuild Request models that reference these param types
# so they pick up our extended versions
mcp_types.CallToolRequest.model_rebuild(force=True)
mcp_types.GetPromptRequest.model_rebuild(force=True)
mcp_types.ReadResourceRequest.model_rebuild(force=True)


# ═══════════════════════════════════════════════════════════════════════════
# Monkey-patch MCP SDK to accept our task request types
# TODO SEP-1686: Remove when SDK officially supports all task methods
# ═══════════════════════════════════════════════════════════════════════════

# Extend ClientRequest and ServerRequest unions to include SEP-1686 task methods.
# This allows both client and server validation to pass for task protocol operations.

# Patch ClientRequest (used by client to send requests)
client_root_field = mcp_types.ClientRequest.model_fields["root"]
client_original_union = client_root_field.annotation
client_original_types = get_args(client_original_union)

# Build new union with SDK-compatible type names (Python 3.10 compatible syntax)
client_new_union = Union[
    (
        *client_original_types,
        GetTaskRequest,
        GetTaskPayloadRequest,
        ListTasksRequest,
        CancelTaskRequest,
    )
]

client_root_field.annotation = client_new_union
mcp_types.ClientRequest.model_rebuild(force=True)

# Patch ServerRequest (used by server to validate incoming requests)
server_root_field = mcp_types.ServerRequest.model_fields["root"]
server_original_union = server_root_field.annotation
server_original_types = get_args(server_original_union)

# Build new union with SDK-compatible type names (Python 3.10 compatible syntax)
server_new_union = Union[
    (
        *server_original_types,
        GetTaskRequest,
        GetTaskPayloadRequest,
        ListTasksRequest,
        CancelTaskRequest,
    )
]

server_root_field.annotation = server_new_union
mcp_types.ServerRequest.model_rebuild(force=True)

# Patch ServerNotification to include TaskStatusNotification
# This allows the SDK to validate our notifications/tasks/status messages
server_notif_root_field = mcp_types.ServerNotification.model_fields["root"]
server_notif_original_union = server_notif_root_field.annotation
server_notif_original_types = get_args(server_notif_original_union)

# Add TaskStatusNotification to the union
server_notif_new_union = Union[(*server_notif_original_types, TaskStatusNotification)]

server_notif_root_field.annotation = server_notif_new_union
mcp_types.ServerNotification.model_rebuild(force=True)
