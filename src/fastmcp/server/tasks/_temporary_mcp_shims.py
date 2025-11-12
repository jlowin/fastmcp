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
