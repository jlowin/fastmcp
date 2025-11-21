"""
⚠️ TEMPORARY CODE - SEP-1686 WORKAROUNDS FOR MCP SDK LIMITATIONS ⚠️

This file contains workarounds for MCP SDK limitations related to SEP-1686 tasks:

1. Client capability declaration - SDK doesn't support customizing experimental capabilities
2. Task protocol types - SDK doesn't have final task protocol types yet
3. Task notification routing - Custom message handler for notifications/tasks/status

These shims will be removed when the MCP SDK is updated to match the final spec.

DO NOT WRITE TESTS FOR THIS FILE - these are temporary hacks.
"""

import datetime
import weakref
from typing import TYPE_CHECKING, Any, Literal

import mcp.types
import pydantic
from mcp.client.session import (
    SUPPORTED_PROTOCOL_VERSIONS,
    ClientSession,
    _default_elicitation_callback,
    _default_list_roots_callback,
    _default_sampling_callback,
)

from fastmcp.client.messages import Message, MessageHandler

if TYPE_CHECKING:
    from fastmcp.client.client import Client


# ═══════════════════════════════════════════════════════════════════════════
# 1. Client Capability Declaration
# ═══════════════════════════════════════════════════════════════════════════


async def task_capable_initialize(
    session: ClientSession,
) -> mcp.types.InitializeResult:
    """Initialize a session with task capabilities.

    Args:
        session: The ClientSession to initialize

    Returns:
        InitializeResult from the server
    """
    # Build capabilities
    sampling = (
        mcp.types.SamplingCapability()
        if session._sampling_callback != _default_sampling_callback
        else None
    )
    elicitation = (
        mcp.types.ElicitationCapability()
        if session._elicitation_callback != _default_elicitation_callback
        else None
    )
    roots = (
        mcp.types.RootsCapability(listChanged=True)
        if session._list_roots_callback != _default_list_roots_callback
        else None
    )

    # Send initialize request with task capability
    result = await session.send_request(
        mcp.types.ClientRequest(
            mcp.types.InitializeRequest(
                params=mcp.types.InitializeRequestParams(
                    protocolVersion=mcp.types.LATEST_PROTOCOL_VERSION,
                    capabilities=mcp.types.ClientCapabilities(
                        sampling=sampling,
                        elicitation=elicitation,
                        experimental={"tasks": {}},
                        roots=roots,
                    ),
                    clientInfo=session._client_info,
                ),
            )
        ),
        mcp.types.InitializeResult,
    )

    # Validate protocol version
    if result.protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS:
        raise RuntimeError(
            f"Unsupported protocol version from the server: {result.protocolVersion}"
        )

    # Send initialized notification
    await session.send_notification(
        mcp.types.ClientNotification(mcp.types.InitializedNotification())
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. Client-Side Type Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TaskStatusResponse(pydantic.BaseModel):
    """Response from tasks/get endpoint."""

    task_id: str = pydantic.Field(alias="taskId")
    status: Literal["working", "input_required", "completed", "failed", "cancelled"]
    created_at: datetime.datetime = pydantic.Field(alias="createdAt")
    ttl: int | None = pydantic.Field(default=None, alias="ttl")
    poll_interval: int | None = pydantic.Field(default=None, alias="pollInterval")
    status_message: str | None = pydantic.Field(default=None, alias="statusMessage")

    model_config = pydantic.ConfigDict(populate_by_name=True)


class TasksResponse(pydantic.BaseModel):
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
# 3. Task Notification Routing
# ═══════════════════════════════════════════════════════════════════════════


class TaskNotificationHandler(MessageHandler):
    """MessageHandler that routes task status notifications to Task objects."""

    def __init__(self, client: "Client"):
        super().__init__()
        self._client_ref: weakref.ref[Client] = weakref.ref(client)

    async def dispatch(self, message: Message) -> None:
        """Dispatch messages, including task status notifications."""
        # Handle task status notifications
        if isinstance(message, mcp.types.ServerNotification):
            if (
                hasattr(message.root, "method")
                and message.root.method == "notifications/tasks/status"
            ):
                client = self._client_ref()
                if client:
                    client._handle_task_status_notification(message.root)

        # Call parent dispatch for all other messages
        await super().dispatch(message)
