"""SEP-1686 task protocol handlers.

Implements MCP task protocol methods: tasks/get, tasks/result, tasks/list, tasks/cancel, tasks/delete.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import mcp.types
from docket.execution import ExecutionState
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, EmptyResult, ErrorData

from fastmcp.server.tasks._temporary_mcp_shims import GetTaskResult, ListTasksResult
from fastmcp.server.tasks.converters import (
    convert_prompt_result,
    convert_resource_result,
    convert_tool_result,
)
from fastmcp.server.tasks.keys import parse_task_key

if TYPE_CHECKING:
    from fastmcp.server.server import FastMCP

# Map Docket execution states to MCP task status strings
# Per SEP-1686 final spec (line 381): tasks MUST begin in "working" status
DOCKET_TO_MCP_STATE: dict[ExecutionState, str] = {
    ExecutionState.SCHEDULED: "working",  # Initial state per spec
    ExecutionState.QUEUED: "working",  # Initial state per spec
    ExecutionState.RUNNING: "working",
    ExecutionState.COMPLETED: "completed",
    ExecutionState.FAILED: "failed",
    ExecutionState.CANCELLED: "cancelled",
}


async def tasks_get_handler(server: FastMCP, params: dict[str, Any]) -> GetTaskResult:
    """Handle MCP 'tasks/get' request (SEP-1686).

    Args:
        server: FastMCP server instance
        params: Request params containing taskId

    Returns:
        GetTaskResult: Task status response with spec-compliant fields
    """
    import fastmcp.server.context
    from fastmcp.server.tasks._temporary_mcp_shims import GetTaskResult

    async with fastmcp.server.context.Context(fastmcp=server) as ctx:
        client_task_id = params.get("taskId")
        if not client_task_id:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS, message="Missing required parameter: taskId"
                )
            )

        # Get session ID from Context
        session_id = ctx.session_id

        # Get execution from Docket (use instance attribute for cross-task access)
        docket = server._docket
        if docket is None:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message="Background tasks require Docket",
                )
            )

        # Look up full task key and creation timestamp from Redis
        redis_key = f"fastmcp:task:{session_id}:{client_task_id}"
        created_at_key = f"fastmcp:task:{session_id}:{client_task_id}:created_at"
        async with docket.redis() as redis:
            task_key_bytes = await redis.get(redis_key)
            created_at_bytes = await redis.get(created_at_key)

        task_key = None if task_key_bytes is None else task_key_bytes.decode("utf-8")
        created_at = (
            None if created_at_bytes is None else created_at_bytes.decode("utf-8")
        )

        if task_key is None:
            # Task not found - raise error per MCP protocol
            raise ValueError(f"Task {client_task_id} not found")

        execution = await docket.get_execution(task_key)
        if execution is None:
            # Task key exists but no execution - raise error
            raise ValueError(f"Task {client_task_id} execution not found")

        # Sync state from Redis
        await execution.sync()

        # Map Docket state to MCP state
        mcp_state = DOCKET_TO_MCP_STATE.get(execution.state, "failed")

        # Build response (use default ttl since we don't track per-task values)
        # createdAt is REQUIRED per SEP-1686 final spec (line 430)
        # Per spec lines 447-448: SHOULD NOT include related-task metadata in tasks/get
        error_message = None
        status_message = None

        if execution.state == ExecutionState.FAILED:
            try:
                await execution.get_result(timeout=timedelta(seconds=0))
            except Exception as error:
                error_message = str(error)
                status_message = f"Task failed: {error_message}"
        elif execution.progress and execution.progress.message:
            # Extract progress message from Docket if available (spec line 403)
            status_message = execution.progress.message

        return GetTaskResult(
            taskId=client_task_id,
            status=mcp_state,  # type: ignore[arg-type]
            createdAt=created_at,  # type: ignore[arg-type]  # Required ISO 8601 timestamp
            ttl=60000,  # Default value in milliseconds
            pollInterval=1000,
            statusMessage=status_message,  # Optional per spec line 403
        )


async def tasks_result_handler(server: FastMCP, params: dict[str, Any]) -> Any:
    """Handle MCP 'tasks/result' request (SEP-1686).

    Converts raw task return values to MCP types based on task type.

    Args:
        server: FastMCP server instance
        params: Request params containing taskId

    Returns:
        MCP result (CallToolResult, GetPromptResult, or ReadResourceResult)
    """
    import fastmcp.server.context

    async with fastmcp.server.context.Context(fastmcp=server) as ctx:
        client_task_id = params.get("taskId")
        if not client_task_id:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS, message="Missing required parameter: taskId"
                )
            )

        # Get session ID from Context
        session_id = ctx.session_id

        # Get execution from Docket (use instance attribute for cross-task access)
        docket = server._docket
        if docket is None:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message="Background tasks require Docket",
                )
            )

        # Look up full task key from Redis
        redis_key = f"fastmcp:task:{session_id}:{client_task_id}"
        async with docket.redis() as redis:
            task_key_bytes = await redis.get(redis_key)

        task_key = None if task_key_bytes is None else task_key_bytes.decode("utf-8")

        if task_key is None:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Invalid taskId: {client_task_id} not found",
                )
            )

        execution = await docket.get_execution(task_key)
        if execution is None:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Invalid taskId: {client_task_id} not found",
                )
            )

        # Sync state from Redis
        await execution.sync()

        # Check if completed
        if execution.state not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            mcp_state = DOCKET_TO_MCP_STATE.get(execution.state, "failed")
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Task not completed yet (current state: {mcp_state})",
                )
            )

        # Get result from Docket
        try:
            raw_value = await execution.get_result(timeout=timedelta(seconds=0))
        except Exception as error:
            # Task failed - return error result
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=str(error))],
                isError=True,
                _meta={
                    "modelcontextprotocol.io/related-task": {
                        "taskId": client_task_id,
                    }
                },
            )

        # Parse task key to get type and component info
        key_parts = parse_task_key(task_key)
        task_type = key_parts["task_type"]

        # Convert based on task type (pass client_task_id for metadata)
        if task_type == "tool":
            return await convert_tool_result(
                server, raw_value, key_parts["component_identifier"], client_task_id
            )
        elif task_type == "prompt":
            return await convert_prompt_result(
                server, raw_value, key_parts["component_identifier"], client_task_id
            )
        elif task_type == "resource":
            return await convert_resource_result(
                server, raw_value, key_parts["component_identifier"], client_task_id
            )
        else:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Internal error: Unknown task type: {task_type}",
                )
            )


async def tasks_list_handler(
    server: FastMCP, params: dict[str, Any]
) -> ListTasksResult:
    """Handle MCP 'tasks/list' request (SEP-1686).

    Note: With client-side tracking, this returns minimal info.

    Args:
        server: FastMCP server instance
        params: Request params (cursor, limit)

    Returns:
        ListTasksResult: Response with tasks list and pagination
    """
    from fastmcp.server.tasks._temporary_mcp_shims import ListTasksResult

    # Return empty list - client tracks tasks locally
    return ListTasksResult(tasks=[], nextCursor=None)


async def tasks_cancel_handler(
    server: FastMCP, params: dict[str, Any]
) -> GetTaskResult:
    """Handle MCP 'tasks/cancel' request (SEP-1686).

    Cancels a running task, transitioning it to cancelled state.

    Args:
        server: FastMCP server instance
        params: Request params containing taskId

    Returns:
        GetTaskResult: Task status response showing cancelled state
    """
    import fastmcp.server.context
    from fastmcp.server.tasks._temporary_mcp_shims import GetTaskResult

    async with fastmcp.server.context.Context(fastmcp=server) as ctx:
        client_task_id = params.get("taskId")
        if not client_task_id:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS, message="Missing required parameter: taskId"
                )
            )

        # Get session ID from Context
        session_id = ctx.session_id

        docket = server._docket
        if docket is None:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message="Background tasks require Docket",
                )
            )

        # Look up full task key and creation timestamp from Redis
        redis_key = f"fastmcp:task:{session_id}:{client_task_id}"
        created_at_key = f"fastmcp:task:{session_id}:{client_task_id}:created_at"
        async with docket.redis() as redis:
            task_key_bytes = await redis.get(redis_key)
            created_at_bytes = await redis.get(created_at_key)

        task_key = None if task_key_bytes is None else task_key_bytes.decode("utf-8")
        created_at = (
            None if created_at_bytes is None else created_at_bytes.decode("utf-8")
        )

        if task_key is None:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Invalid taskId: {client_task_id} not found",
                )
            )

        # Check if task exists
        execution = await docket.get_execution(task_key)
        if execution is None:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Invalid taskId: {client_task_id} not found",
                )
            )

        # Cancel via Docket (now sets CANCELLED state natively)
        await docket.cancel(task_key)

        # Return task status with cancelled state
        # createdAt is REQUIRED per SEP-1686 final spec (line 430)
        # Per spec lines 447-448: SHOULD NOT include related-task metadata in tasks/cancel
        return GetTaskResult(
            taskId=client_task_id,
            status="cancelled",
            createdAt=created_at or datetime.now(timezone.utc).isoformat(),
            ttl=None,
            pollInterval=1000,
            error=None,
            statusMessage="Task cancelled",  # Optional per spec line 403
        )


async def tasks_delete_handler(server: FastMCP, params: dict[str, Any]) -> EmptyResult:
    """Handle MCP 'tasks/delete' request (SEP-1686).

    Deletion is discretionary - we allow deletion of any task.

    Args:
        server: FastMCP server instance
        params: Request params containing taskId

    Returns:
        EmptyResult: Response with related-task metadata
    """
    from mcp.types import EmptyResult

    import fastmcp.server.context

    async with fastmcp.server.context.Context(fastmcp=server) as ctx:
        client_task_id = params.get("taskId")
        if not client_task_id:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS, message="Missing required parameter: taskId"
                )
            )

        # Get session ID from Context
        session_id = ctx.session_id

        docket = server._docket
        if docket is None:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message="Background tasks require Docket",
                )
            )

        # Look up full task key from Redis
        redis_key = f"fastmcp:task:{session_id}:{client_task_id}"
        async with docket.redis() as redis:
            task_key_bytes = await redis.get(redis_key)

        task_key = None if task_key_bytes is None else task_key_bytes.decode("utf-8")

        if task_key is None:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Invalid taskId: {client_task_id} not found",
                )
            )

        # Check if task exists
        execution = await docket.get_execution(task_key)
        if execution is None:
            raise McpError(
                ErrorData(
                    code=INVALID_PARAMS,
                    message=f"Invalid taskId: {client_task_id} not found",
                )
            )

        # Cancel via Docket (Docket handles cleanup via TTL)
        await docket.cancel(task_key)

        # Remove task key mapping from Redis
        async with docket.redis() as redis:
            await redis.delete(redis_key)

        # Return empty response with related-task metadata
        return EmptyResult(
            _meta={
                "modelcontextprotocol.io/related-task": {
                    "taskId": client_task_id,
                }
            }
        )


def setup_task_protocol_handlers(server: FastMCP) -> None:
    """Register SEP-1686 task protocol handlers with the MCP server.

    Creates wrapper functions that pass the FastMCP server instance to handlers.

    Args:
        server: FastMCP server instance
    """

    from fastmcp.server.tasks._temporary_mcp_shims import (
        CancelTaskRequest,
        DeleteTaskRequest,
        GetTaskPayloadRequest,
        GetTaskRequest,
        ListTasksRequest,
    )

    # Create wrappers that adapt Request objects to dict params and wrap results
    async def tasks_get_wrapper(req: GetTaskRequest) -> mcp.types.ServerResult:
        params_dict = req.params.model_dump(by_alias=True, exclude_none=True)
        result = await tasks_get_handler(server, params_dict)
        # Serialize typed result to dict for ServerResult compatibility
        result_dict = result.model_dump(by_alias=True, exclude_none=True)
        return mcp.types.ServerResult(root=result_dict)  # type: ignore[arg-type]

    async def tasks_result_wrapper(
        req: GetTaskPayloadRequest,
    ) -> mcp.types.ServerResult:
        params_dict = req.params.model_dump(by_alias=True, exclude_none=True)
        result = await tasks_result_handler(server, params_dict)
        return mcp.types.ServerResult(root=result)  # type: ignore[arg-type]

    async def tasks_list_wrapper(req: ListTasksRequest) -> mcp.types.ServerResult:
        params_dict = (
            req.params.model_dump(by_alias=True, exclude_none=True)
            if req.params
            else {}
        )  # type: ignore[union-attr]
        result = await tasks_list_handler(server, params_dict)
        # Serialize typed result to dict for ServerResult compatibility
        result_dict = result.model_dump(by_alias=True, exclude_none=True)
        return mcp.types.ServerResult(root=result_dict)  # type: ignore[arg-type]

    async def tasks_cancel_wrapper(req: CancelTaskRequest) -> mcp.types.ServerResult:
        params_dict = req.params.model_dump(by_alias=True, exclude_none=True)
        result = await tasks_cancel_handler(server, params_dict)
        # Serialize typed result to dict for ServerResult compatibility
        result_dict = result.model_dump(by_alias=True, exclude_none=True)
        return mcp.types.ServerResult(root=result_dict)  # type: ignore[arg-type]

    async def tasks_delete_wrapper(req: DeleteTaskRequest) -> mcp.types.ServerResult:
        params_dict = req.params.model_dump(by_alias=True, exclude_none=True)
        result = await tasks_delete_handler(server, params_dict)
        # Serialize typed result to dict for ServerResult compatibility
        result_dict = result.model_dump(by_alias=True, exclude_none=True)
        return mcp.types.ServerResult(root=result_dict)  # type: ignore[arg-type]

    # Register handlers with MCP server (using SDK-compatible type names)
    server._mcp_server.request_handlers[GetTaskRequest] = tasks_get_wrapper
    server._mcp_server.request_handlers[GetTaskPayloadRequest] = tasks_result_wrapper
    server._mcp_server.request_handlers[ListTasksRequest] = tasks_list_wrapper
    server._mcp_server.request_handlers[CancelTaskRequest] = tasks_cancel_wrapper
    server._mcp_server.request_handlers[DeleteTaskRequest] = tasks_delete_wrapper
