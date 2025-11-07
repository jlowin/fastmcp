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
from typing import Any

from fastmcp.server.tasks._temporary_docket_shims import (
    get_result,
    get_state,
)
from fastmcp.server.tasks._temporary_docket_shims import (
    set_state as _set_state_docket,
)

# HACK: Task ID mapping for FastMCPTransport
# Maps client-provided task IDs → full task keys (with type and component embedded)
# Needed because MCP SDK's custom protocol handlers don't receive session context
_task_id_mapping: dict[str, str] = {}
_lock = asyncio.Lock()


async def set_state(
    task_key: str,
    state: str,
    keep_alive: int | None = None,
    client_task_id: str | None = None,
) -> None:
    """Set task state and optionally register task ID mapping.

    Wrapper around Docket's set_state that also handles MCP SDK's task ID mapping.

    Args:
        task_key: Full task key (with type and component embedded)
        state: Task state (submitted, working, completed, failed)
        keep_alive: Optional keep_alive to store (needed for result expiration)
        client_task_id: Optional client task ID to register in mapping (MCP SDK hack)
    """
    await _set_state_docket(task_key, state, keep_alive=keep_alive)
    if client_task_id:
        await register_task_id(client_task_id, task_key)


async def register_task_id(client_task_id: str, task_key: str) -> None:
    """Register a client task ID mapping (HACK for FastMCPTransport).

    TODO: Remove when MCP SDK provides request context to custom protocol methods

    Args:
        client_task_id: Client-provided task ID
        task_key: Full task key (with type and component embedded)
    """
    async with _lock:
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


async def get_task_status_dict(task_id: str) -> dict[str, Any] | None:
    """Get task status as dict without server context (HACK for FastMCPTransport).

    The MCP SDK doesn't provide request context to custom protocol methods,
    so we need context-free helpers that use the task ID mapping.

    TODO: Remove when MCP SDK provides request context to custom protocol methods

    Args:
        task_id: Client task ID (will be resolved to full task key)

    Returns:
        Status dict or None if task not found
    """
    from fastmcp.server.tasks._temporary_docket_shims import (
        _lock as docket_lock,
    )
    from fastmcp.server.tasks._temporary_docket_shims import (
        _task_keep_alive,
    )

    task_key = await resolve_task_id(task_id)
    if task_key is None:
        return None

    state = await get_state(task_key)
    if state is None:
        return None

    # Get keepAlive from storage (MUST return in all responses per spec)
    async with docket_lock:
        keep_alive_value = _task_keep_alive.get(task_key, 60000)

    status = {
        "status": state,
        "keepAlive": keep_alive_value,  # Always include per spec
        "pollFrequency": 1000,
    }

    result_record = await get_result(task_key)
    if result_record and result_record.error:
        status["error"] = str(result_record.error)

    return status


async def get_task_result_raw(task_id: str):
    """Get task result without server context (HACK for FastMCPTransport).

    TODO: Remove when MCP SDK provides request context to custom protocol methods

    Args:
        task_id: Client task ID (will be resolved to full task key)

    Returns:
        TaskResult object or None if not found

    Raises:
        ValueError: If task not completed
    """
    task_key = await resolve_task_id(task_id)
    if task_key is None:
        return None

    result_record = await get_result(task_key)
    if result_record is None:
        state = await get_state(task_key)
        if state is None:
            return None
        else:
            raise ValueError(f"Task not completed yet (state: {state})")

    return result_record


async def cancel_task(task_id: str) -> bool:
    """Cancel a task without server context (HACK for FastMCPTransport).

    Transitions task to cancelled state without deleting it.

    TODO: Remove when MCP SDK provides request context to custom protocol methods

    Args:
        task_id: Client task ID (will be resolved to full task key)

    Returns:
        True if task was found and cancelled, False if not found
    """
    from fastmcp.server.tasks._temporary_docket_shims import (
        cancel_task as _cancel_task_docket,
    )

    task_key = await resolve_task_id(task_id)
    if task_key is None:
        return False

    # Cancel via Docket shims (sets state to cancelled)
    return await _cancel_task_docket(task_key)


async def delete_task(task_id: str) -> bool:
    """Delete a task without server context (HACK for FastMCPTransport).

    TODO: Remove when MCP SDK provides request context to custom protocol methods

    Args:
        task_id: Client task ID (will be resolved to full task key)

    Returns:
        True if task was found and deleted, False if not found
    """
    from fastmcp.server.tasks._temporary_docket_shims import (
        delete_task as _delete_task_docket,
    )

    task_key = await resolve_task_id(task_id)
    if task_key is None:
        return False

    # Delete from Docket shims
    deleted = await _delete_task_docket(task_key)

    # Also remove from task ID mapping
    if deleted:
        async with _lock:
            _task_id_mapping.pop(task_id, None)

    return deleted
