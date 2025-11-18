"""Task subscription helpers for sending MCP notifications (SEP-1686).

Subscribes to Docket execution state changes and sends notifications/tasks/status
to clients when their tasks change state.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from docket.execution import ExecutionState

from fastmcp.server.tasks._temporary_mcp_shims import (
    TaskStatusNotification,
    TaskStatusNotificationParams,
)
from fastmcp.server.tasks.protocol import DOCKET_TO_MCP_STATE
from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from docket import Docket
    from mcp.server.session import ServerSession

logger = get_logger(__name__)


async def subscribe_to_task_updates(
    task_id: str,
    task_key: str,
    session: ServerSession,
    docket: Docket,
) -> None:
    """Subscribe to Docket execution events and send MCP notifications.

    Per SEP-1686 lines 436-444, servers MAY send notifications/tasks/status
    when task state changes. This is an optional optimization that reduces
    client polling frequency.

    Args:
        task_id: Client-visible task ID (server-generated UUID)
        task_key: Internal Docket execution key (includes session, type, component)
        session: MCP ServerSession for sending notifications
        docket: Docket instance for subscribing to execution events
    """
    try:
        logger.info(f"[SUBSCRIPTION] Starting for task {task_id}, key={task_key}")
        execution = await docket.get_execution(task_key)
        if execution is None:
            logger.warning(f"No execution found for task {task_id}")
            return

        logger.debug(f"Starting subscription for task {task_id}")

        # Subscribe to state and progress events from Docket
        # This is an AsyncGenerator that yields events until task completes
        async for event in execution.subscribe():
            if event["type"] == "state":
                # Send notifications/tasks/status when state changes
                await _send_status_notification(
                    session=session,
                    task_id=task_id,
                    task_key=task_key,
                    docket=docket,
                    state=event["state"],  # type: ignore[typeddict-item]
                    error=event.get("error"),  # type: ignore[typeddict-item]
                )
            elif event["type"] == "progress":
                # Progress events available but not used yet
                # Could send progress notifications here if needed
                pass

        logger.info(f"[SUBSCRIPTION] Ended for task {task_id}")

    except Exception as e:
        logger.warning(f"Subscription task failed for {task_id}: {e}", exc_info=True)


async def _send_status_notification(
    session: ServerSession,
    task_id: str,
    task_key: str,
    docket: Docket,
    state: ExecutionState,
    error: str | None = None,
) -> None:
    """Send notifications/tasks/status to client.

    Per SEP-1686 line 454: notification SHOULD NOT include related-task metadata
    (taskId is already in params).

    Args:
        session: MCP ServerSession
        task_id: Client-visible task ID
        task_key: Internal task key (for metadata lookup)
        docket: Docket instance
        state: Docket execution state (enum)
        error: Error message if task failed
    """
    # Map Docket state to MCP status
    mcp_status = DOCKET_TO_MCP_STATE.get(state, "unknown")

    # Extract session_id from task_key for Redis lookup
    from fastmcp.server.tasks.keys import parse_task_key

    key_parts = parse_task_key(task_key)
    session_id = key_parts["session_id"]

    # Retrieve createdAt timestamp from Redis
    created_at_key = f"fastmcp:task:{session_id}:{task_id}:created_at"
    async with docket.redis() as redis:
        created_at_bytes = await redis.get(created_at_key)

    created_at = (
        created_at_bytes.decode("utf-8")
        if created_at_bytes
        else datetime.now(timezone.utc).isoformat()
    )

    # Build status message
    status_message = None
    if state == ExecutionState.COMPLETED:
        status_message = "Task completed successfully"
    elif state == ExecutionState.FAILED:
        status_message = f"Task failed: {error}" if error else "Task failed"
    elif state == ExecutionState.CANCELLED:
        status_message = "Task cancelled"

    # Construct notification params (full Task object per spec lines 264, 452-454)
    params_dict = {
        "taskId": task_id,
        "status": mcp_status,
        "createdAt": created_at,
        "ttl": 60000,  # Default TTL
        "pollInterval": 1000,
    }

    if error:
        params_dict["error"] = error
    if status_message:
        params_dict["statusMessage"] = status_message

    # Create notification (no related-task metadata per spec line 454)
    notification = TaskStatusNotification(
        params=TaskStatusNotificationParams.model_validate(params_dict),
    )

    # Send notification (don't let failures break the subscription)
    with suppress(Exception):
        await session.send_notification(notification)  # type: ignore[arg-type]
