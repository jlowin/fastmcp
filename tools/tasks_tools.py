# ruff: noqa: BLE001, F841
"""
Tasks Management Tools for MCP Server

These tools allow AI agents to manage tasks through the FastAPI backend.
"""

import json

from fastmcp import Context, FastMCP

try:
    from ..auth_utils import convert_user_id_to_token, make_authenticated_request
except ImportError:  # Standalone repository layout
    from auth_utils import convert_user_id_to_token, make_authenticated_request


def register_tasks_tools(mcp: FastMCP):
    """Register all tasks-related tools with the MCP server."""

    @mcp.tool()
    async def create_task(
        title: str,
        description: str = "",
        status: str = "todo",
        user_id: str = "demo-user",
        ctx: Context = None,
    ) -> str:
        """
        Create a new task with the given title and description.

        Args:
            title: The title of the task (required)
            description: The description of the task (optional)
            status: Task status - one of: todo, in_progress, done (default: todo)
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with the created task details
        """
        if ctx:
            await ctx.info(f"Creating task with title: {title}")

        # Validate status
        valid_statuses = ["todo", "in_progress", "done"]
        if status not in valid_statuses:
            error_msg = f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

        try:
            # Convert user_id to token if needed
            token = await convert_user_id_to_token(user_id)

            task_data = {"title": title, "description": description, "status": status}

            result = await make_authenticated_request(
                "POST", "/api/v1/tasks/", token, task_data
            )

            if ctx:
                await ctx.info(f"Successfully created task with ID: {result.get('id')}")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to create task: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_tasks(
        user_id: str = "demo-user",
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
        ctx: Context = None,
    ) -> str:
        """
        Retrieve tasks for the user, optionally filtered by status.

        Args:
            user_id: User ID (default: demo-user)
            status: Filter by status - one of: todo, in_progress, done (optional)
            skip: Number of tasks to skip (for pagination)
            limit: Maximum number of tasks to return

        Returns:
            JSON string with list of tasks
        """
        if ctx:
            await ctx.info(f"Retrieving tasks for user: {user_id}")

        try:
            params = {"skip": skip, "limit": limit}
            if status:
                params["status"] = status

            result = await make_authenticated_request(
                "GET", "/api/v1/tasks/", user_id, params=params
            )

            if ctx:
                await ctx.info(f"Retrieved {len(result.get('data', []))} tasks")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to retrieve tasks: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def update_task(
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        user_id: str = "demo-user",
        ctx: Context = None,
    ) -> str:
        """
        Update an existing task.

        Args:
            task_id: UUID of the task to update
            title: New title for the task (optional)
            description: New description for the task (optional)
            status: New status - one of: todo, in_progress, done (optional)
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with the updated task details
        """
        if ctx:
            await ctx.info(f"Updating task: {task_id}")

        # Validate status if provided
        if status:
            valid_statuses = ["todo", "in_progress", "done"]
            if status not in valid_statuses:
                error_msg = (
                    f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                )
                if ctx:
                    await ctx.error(error_msg)
                return json.dumps({"error": error_msg})

        try:
            update_data = {}
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if status is not None:
                update_data["status"] = status

            result = await make_authenticated_request(
                "PUT", f"/api/v1/tasks/{task_id}", user_id, update_data
            )

            if ctx:
                await ctx.info(f"Successfully updated task: {task_id}")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to update task: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def complete_task(
        task_id: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Mark a task as completed (status = done).

        Args:
            task_id: UUID of the task to complete
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with the updated task details
        """
        if ctx:
            await ctx.info(f"Completing task: {task_id}")

        try:
            update_data = {"status": "done"}

            result = await make_authenticated_request(
                "PUT", f"/api/v1/tasks/{task_id}", user_id, update_data
            )

            if ctx:
                await ctx.info(f"Successfully completed task: {task_id}")

            return json.dumps(result, default=str)

        except Exception as e:
            error_msg = f"Failed to complete task: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def delete_task(
        task_id: str, user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Delete a task by ID.

        Args:
            task_id: UUID of the task to delete
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with deletion confirmation
        """
        if ctx:
            await ctx.info(f"Deleting task: {task_id}")

        try:
            result = await make_authenticated_request(
                "DELETE", f"/api/v1/tasks/{task_id}", user_id
            )

            if ctx:
                await ctx.info(f"Successfully deleted task: {task_id}")

            return json.dumps({"message": f"Task {task_id} deleted successfully"})

        except Exception as e:
            error_msg = f"Failed to delete task: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})

    @mcp.tool()
    async def get_task_statistics(
        user_id: str = "demo-user", ctx: Context = None
    ) -> str:
        """
        Get task statistics (count by status) for the user.

        Args:
            user_id: User ID (default: demo-user)

        Returns:
            JSON string with task statistics
        """
        if ctx:
            await ctx.info(f"Getting task statistics for user: {user_id}")

        try:
            result = await make_authenticated_request(
                "GET",
                "/api/v1/tasks/",
                user_id,
                params={"limit": 1000},  # Get all tasks
            )

            tasks = result.get("data", [])

            # Calculate statistics
            stats = {
                "total": len(tasks),
                "todo": len([t for t in tasks if t.get("status") == "todo"]),
                "in_progress": len(
                    [t for t in tasks if t.get("status") == "in_progress"]
                ),
                "done": len([t for t in tasks if t.get("status") == "done"]),
            }

            # Add completion percentage
            if stats["total"] > 0:
                stats["completion_percentage"] = round(
                    (stats["done"] / stats["total"]) * 100, 1
                )
            else:
                stats["completion_percentage"] = 0

            if ctx:
                await ctx.info(
                    f"Task statistics calculated: {stats['total']} total tasks"
                )

            return json.dumps(stats, default=str)

        except Exception as e:
            error_msg = f"Failed to get task statistics: {str(e)}"
            if ctx:
                await ctx.error(error_msg)
            return json.dumps({"error": error_msg})
