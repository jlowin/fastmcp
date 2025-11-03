"""
⚠️ TEMPORARY CODE - WORKAROUND FOR MCP SDK CLIENT CAPABILITY LIMITATION ⚠️

This file contains a workaround for the MCP SDK's inability to customize client
capabilities. Specifically, ClientSession.initialize() hard-codes experimental=None.

Per SEP-1686, clients MUST declare task capability in experimental.tasks, but
the SDK doesn't provide a way to customize this.

This shim will be removed when:
- MCP SDK adds support for customizing ClientCapabilities.experimental, OR
- MCP SDK adds a client_capabilities parameter to ClientSession.__init__

DO NOT WRITE TESTS FOR THIS FILE - it's a temporary hack that will be deleted.
"""

from typing import TYPE_CHECKING

import mcp.types
from mcp.client.session import (
    SUPPORTED_PROTOCOL_VERSIONS,
    ClientSession,
    _default_elicitation_callback,
    _default_list_roots_callback,
    _default_sampling_callback,
)

if TYPE_CHECKING:
    pass


class TaskCapableClientSession(ClientSession):
    """
    Custom ClientSession that declares task capability.

    Overrides initialize() to set experimental={"tasks": True} in ClientCapabilities.
    This is the ONLY difference from the base ClientSession - everything else is identical.

    TODO: Delete this entire class when MCP SDK supports customizing client capabilities
    """

    async def initialize(self) -> mcp.types.InitializeResult:
        """Initialize with task capability declaration.

        This is a copy of ClientSession.initialize() with one change:
        experimental={"tasks": True} instead of experimental=None
        """
        # Build capabilities (same as SDK)
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
                            experimental={
                                "tasks": {}
                            },  # ← ONLY CHANGE FROM SDK (empty dict per spec)
                            roots=roots,
                        ),
                        clientInfo=self._client_info,
                    ),
                )
            ),
            mcp.types.InitializeResult,
        )

        # Validate protocol version (same as SDK)
        if result.protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS:
            raise RuntimeError(
                f"Unsupported protocol version from the server: {result.protocolVersion}"
            )

        # Send initialized notification (same as SDK)
        await self.send_notification(
            mcp.types.ClientNotification(mcp.types.InitializedNotification())
        )

        return result


async def task_capable_initialize(session: ClientSession) -> mcp.types.InitializeResult:
    """Standalone function to initialize a session with task capabilities.

    Calls the same logic as TaskCapableClientSession.initialize() but as a
    standalone function that can be called with any ClientSession instance.

    Args:
        session: The ClientSession to initialize

    Returns:
        InitializeResult from the server
    """
    # Build capabilities (same as SDK)
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
                        experimental={
                            "tasks": {}
                        },  # ← ONLY CHANGE FROM SDK (empty dict per spec)
                        roots=roots,
                    ),
                    clientInfo=session._client_info,
                ),
            )
        ),
        mcp.types.InitializeResult,
    )

    # Validate protocol version (same as SDK)
    if result.protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS:
        raise RuntimeError(
            f"Unsupported protocol version from the server: {result.protocolVersion}"
        )

    # Send initialized notification (same as SDK)
    await session.send_notification(
        mcp.types.ClientNotification(mcp.types.InitializedNotification())
    )

    return result
