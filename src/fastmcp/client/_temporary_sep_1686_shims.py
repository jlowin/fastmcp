"""
⚠️ TEMPORARY CODE - SEP-1686 WORKAROUNDS FOR MCP SDK LIMITATIONS ⚠️

This file contains workarounds for MCP SDK limitations related to SEP-1686 tasks:

1. Client capability declaration - SDK doesn't support customizing experimental capabilities
2. Task protocol types - SDK doesn't have final task protocol types yet
3. Task notification routing - Custom message handler for notifications/tasks/status

These shims will be removed when the MCP SDK is updated to match the final spec.

DO NOT WRITE TESTS FOR THIS FILE - these are temporary hacks.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass
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
from pydantic import BaseModel

from fastmcp.client.messages import Message, MessageHandler

if TYPE_CHECKING:
    from fastmcp.client.client import Client


# ═══════════════════════════════════════════════════════════════════════════
# 1. Client Capability Declaration
# ═══════════════════════════════════════════════════════════════════════════


class TaskCapableClientSession(ClientSession):
    """Custom ClientSession that declares task capability.

    Overrides initialize() to set experimental={"tasks": {}} in ClientCapabilities.
    """

    async def initialize(self) -> mcp.types.InitializeResult:
        """Initialize with task capability declaration."""
        # Build capabilities
        sampling = (
            mcp.types.SamplingCapability()
            if self._sampling_callback != _default_sampling_callback
            else None
        )
        elicitation = (
            mcp.types.ElicitationCapability()
            if self._elicitation_callback != _default_elicitation_callback
            else None
        )
        roots = (
            mcp.types.RootsCapability(listChanged=True)
            if self._list_roots_callback != _default_list_roots_callback
            else None
        )

        # Send initialize request with task capability
        result = await self.send_request(
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
                        clientInfo=self._client_info,
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
        await self.send_notification(
            mcp.types.ClientNotification(mcp.types.InitializedNotification())
        )

        return result


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
# 2. Task Protocol Types (SDK doesn't have these yet)
# ═══════════════════════════════════════════════════════════════════════════


class TasksGetRequest(BaseModel):
    """Request for tasks/get MCP method."""

    method: Literal["tasks/get"] = "tasks/get"
    params: TasksGetParams


class TasksGetParams(BaseModel):
    """Parameters for tasks/get request."""

    taskId: str
    _meta: dict[str, Any] | None = None


class TasksGetResult(BaseModel):
    """Result from tasks/get MCP method."""

    taskId: str
    status: Literal["working", "input_required", "completed", "failed", "cancelled"]
    createdAt: str
    ttl: int | None = None
    pollInterval: int | None = None


class TasksResultRequest(BaseModel):
    """Request for tasks/result MCP method."""

    method: Literal["tasks/result"] = "tasks/result"
    params: TasksResultParams


class TasksResultParams(BaseModel):
    """Parameters for tasks/result request."""

    taskId: str
    _meta: dict[str, Any] | None = None


class TasksListRequest(BaseModel):
    """Request for tasks/list MCP method."""

    method: Literal["tasks/list"] = "tasks/list"
    params: TasksListParams


class TasksListParams(BaseModel):
    """Parameters for tasks/list request."""

    cursor: str | None = None
    limit: int = 50
    _meta: dict[str, Any] | None = None


class TasksListResult(BaseModel):
    """Result from tasks/list MCP method."""

    tasks: list[dict[str, Any]]
    nextCursor: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Client-Side Type Helpers
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class CallToolResult:
    """Parsed result from a tool call."""

    content: list[mcp.types.ContentBlock]
    structured_content: dict[str, Any] | None
    meta: dict[str, Any] | None
    data: Any = None
    is_error: bool = False


class TaskStatusResponse(pydantic.BaseModel):
    """Response from tasks/get endpoint."""

    task_id: str = pydantic.Field(alias="taskId")
    status: Literal["working", "input_required", "completed", "failed", "cancelled"]
    created_at: str = pydantic.Field(alias="createdAt")
    ttl: int | None = pydantic.Field(default=None, alias="ttl")
    poll_interval: int | None = pydantic.Field(default=None, alias="pollInterval")
    status_message: str | None = pydantic.Field(default=None, alias="statusMessage")

    model_config = pydantic.ConfigDict(populate_by_name=True)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Task Notification Routing
# ═══════════════════════════════════════════════════════════════════════════


class ClientMessageHandler(MessageHandler):
    """MessageHandler that routes task status notifications to Task objects."""

    def __init__(self, client: Client):
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
