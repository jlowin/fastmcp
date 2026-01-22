"""Task routing helper for MCP components.

Provides unified task mode enforcement and docket routing logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import mcp.types
from mcp.shared.exceptions import McpError
from mcp.types import METHOD_NOT_FOUND, ErrorData

from fastmcp.server.dependencies import requires_docket_execution
from fastmcp.server.tasks.config import TaskMeta
from fastmcp.server.tasks.handlers import run_in_docket_sync, submit_to_docket

if TYPE_CHECKING:
    from fastmcp.prompts.prompt import Prompt, PromptResult
    from fastmcp.resources.resource import Resource, ResourceResult
    from fastmcp.resources.template import ResourceTemplate
    from fastmcp.tools.tool import Tool, ToolResult

TaskType = Literal["tool", "resource", "template", "prompt"]


async def check_background_task(
    component: Tool | Resource | ResourceTemplate | Prompt,
    task_type: TaskType,
    arguments: dict[str, Any] | None = None,
    task_meta: TaskMeta | None = None,
) -> mcp.types.CreateTaskResult | ToolResult | ResourceResult | PromptResult | None:
    """Check task mode and submit to background if requested.

    Also handles auto-routing for components with Docket dependencies:
    if a component uses Timeout, Retry, etc. and wasn't explicitly requested
    as a background task, we run it through Docket with sync-wait semantics.

    Args:
        component: The MCP component
        task_type: Type of task ("tool", "resource", "template", "prompt")
        arguments: Arguments for tool/prompt/template execution
        task_meta: Task execution metadata. If provided, execute as background task.

    Returns:
        CreateTaskResult if submitted to docket as background task,
        ToolResult/ResourceResult/PromptResult if auto-routed through Docket sync,
        None for regular sync execution

    Raises:
        McpError: If mode="required" but no task metadata, or mode="forbidden"
                  but task metadata is present
    """
    task_config = component.task_config

    # Infer label from component
    entity_label = f"{type(component).__name__} '{component.title or component.key}'"

    # Enforce mode="required" - must have task metadata
    if task_config.mode == "required" and not task_meta:
        raise McpError(
            ErrorData(
                code=METHOD_NOT_FOUND,
                message=f"{entity_label} requires task-augmented execution",
            )
        )

    # Enforce mode="forbidden" - cannot be called with task metadata
    if not task_config.supports_tasks() and task_meta:
        raise McpError(
            ErrorData(
                code=METHOD_NOT_FOUND,
                message=f"{entity_label} does not support task-augmented execution",
            )
        )

    # Auto-route through Docket if component has Docket dependencies
    # This ensures Timeout, Retry, etc. work even for foreground calls
    if not task_meta and requires_docket_execution(component):
        return await run_in_docket_sync(task_type, component, arguments)

    # No task metadata - regular synchronous execution
    if not task_meta:
        return None

    # fn_key is expected to be set; fall back to component.key for direct calls
    fn_key = task_meta.fn_key or component.key
    return await submit_to_docket(task_type, fn_key, component, arguments, task_meta)
