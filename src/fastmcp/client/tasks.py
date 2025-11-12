"""SEP-1686 task protocol types and client Task classes."""

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

import mcp.types
import pydantic
from pydantic import BaseModel

if TYPE_CHECKING:
    from fastmcp.client.client import Client


class TasksGetRequest(BaseModel):
    """Request for tasks/get MCP method."""

    method: Literal["tasks/get"] = "tasks/get"
    params: "TasksGetParams"


class TasksGetParams(BaseModel):
    """Parameters for tasks/get request."""

    taskId: str
    _meta: dict[str, Any] | None = None


class TasksGetResult(BaseModel):
    """Result from tasks/get MCP method."""

    taskId: str
    status: Literal[
        "submitted", "working", "completed", "failed", "cancelled", "unknown"
    ]
    keepAlive: int | None = None
    pollFrequency: int | None = None
    error: str | None = None


class TasksResultRequest(BaseModel):
    """Request for tasks/result MCP method."""

    method: Literal["tasks/result"] = "tasks/result"
    params: "TasksResultParams"


class TasksResultParams(BaseModel):
    """Parameters for tasks/result request."""

    taskId: str
    _meta: dict[str, Any] | None = None


class TasksListRequest(BaseModel):
    """Request for tasks/list MCP method."""

    method: Literal["tasks/list"] = "tasks/list"
    params: "TasksListParams"


class TasksListParams(BaseModel):
    """Parameters for tasks/list request."""

    cursor: str | None = None
    limit: int = 50
    _meta: dict[str, Any] | None = None


class TasksListResult(BaseModel):
    """Result from tasks/list MCP method."""

    tasks: list[dict[str, Any]]
    nextCursor: str | None = None


class TasksDeleteRequest(BaseModel):
    """Request for tasks/delete MCP method."""

    method: Literal["tasks/delete"] = "tasks/delete"
    params: "TasksDeleteParams"


class TasksDeleteParams(BaseModel):
    """Parameters for tasks/delete request."""

    taskId: str
    _meta: dict[str, Any] | None = None


class TasksDeleteResult(BaseModel):
    """Result from tasks/delete MCP method."""

    _meta: dict[str, Any] | None = None


# Task execution classes


@dataclass
class CallToolResult:
    """Parsed result from a tool call."""

    content: list[mcp.types.ContentBlock]
    structured_content: dict[str, Any] | None
    meta: dict[str, Any] | None
    data: Any = None
    is_error: bool = False


TaskResultT = TypeVar("TaskResultT")


class TaskStatusResponse(pydantic.BaseModel):
    """Response from tasks/get endpoint (SEP-1686)."""

    task_id: str = pydantic.Field(alias="taskId")
    """The task identifier."""

    status: Literal[
        "submitted", "working", "completed", "failed", "cancelled", "unknown"
    ]
    """Current task state."""

    keep_alive: int | None = pydantic.Field(default=None, alias="keepAlive")
    """Actual retention duration in milliseconds after completion, None for unlimited."""

    poll_frequency: int | None = pydantic.Field(default=None, alias="pollFrequency")
    """Suggested polling interval in milliseconds."""

    error: str | None = None
    """Error message if status is 'failed'."""

    model_config = pydantic.ConfigDict(populate_by_name=True)


class Task(abc.ABC, Generic[TaskResultT]):
    """
    Abstract base class for MCP background tasks (SEP-1686).

    Provides a uniform API whether the server accepts background execution
    or executes synchronously (graceful degradation per SEP-1686).

    Subclasses:
        - ToolTask: For tool calls (result type: CallToolResult)
        - PromptTask: For prompts (future, result type: GetPromptResult)
        - ResourceTask: For resources (future, result type: ReadResourceResult)
    """

    def __init__(
        self,
        client: "Client",
        task_id: str,
        immediate_result: TaskResultT | None = None,
    ):
        """
        Create a Task wrapper.

        Args:
            client: The FastMCP client
            task_id: The task identifier
            immediate_result: If server executed synchronously, the immediate result
        """
        self._client = client
        self._task_id = task_id
        self._immediate_result = immediate_result
        self._is_immediate = immediate_result is not None
        self._cached_result: TaskResultT | None = None

    def _check_client_connected(self) -> None:
        """Validate that client context is still active.

        Raises:
            RuntimeError: If accessed outside client context (unless immediate)
        """
        if self._is_immediate:
            return  # Already resolved, no client needed

        try:
            _ = self._client.session
        except RuntimeError as e:
            raise RuntimeError(
                "Cannot access task results outside client context. "
                "Task futures must be used within 'async with client:' block."
            ) from e

    @property
    def task_id(self) -> str:
        """Get the task ID."""
        return self._task_id

    @property
    def returned_immediately(self) -> bool:
        """Check if server executed the task immediately.

        Returns:
            True if server executed synchronously (graceful degradation or no task support)
            False if server accepted background execution
        """
        return self._is_immediate

    async def status(self) -> TaskStatusResponse:
        """Get current task status.

        If server executed immediately, returns synthetic completed status.
        Otherwise queries the server for current status.
        """
        self._check_client_connected()

        if self._is_immediate:
            # Return synthetic completed status
            return TaskStatusResponse(
                taskId=self._task_id,  # Use alias field name
                status="completed",
                keepAlive=None,
                pollFrequency=1000,  # Include poll frequency even for immediate results
            )
        return await self._client.get_task_status(self._task_id)

    @abc.abstractmethod
    async def result(self) -> TaskResultT:
        """Wait for and return the task result.

        Must be implemented by subclasses to return the appropriate result type.
        """
        ...

    async def wait(
        self, *, state: str | None = None, timeout: float = 300.0
    ) -> TaskStatusResponse:
        """Wait for task to reach a specific state or complete.

        If server executed immediately, returns immediately.
        Otherwise polls until desired state is reached.

        Args:
            state: Desired state ('submitted', 'working', 'completed', 'failed').
                   If None, waits for any terminal state (completed/failed)
            timeout: Maximum time to wait in seconds

        Returns:
            TaskStatusResponse: Final task status
        """
        self._check_client_connected()

        if self._is_immediate:
            # Already done
            return await self.status()
        return await self._client.wait_for_task(
            self._task_id, state=state, timeout=timeout
        )

    async def cancel(self) -> None:
        """Cancel this task, transitioning it to cancelled state.

        Requests cancellation via notifications/cancelled. The server will attempt
        to halt execution and move the task to cancelled state.

        Note: If server executed immediately (graceful degradation), this is a no-op
        as there's no server-side task to cancel.
        """
        if self._is_immediate:
            # No server-side task to cancel
            return
        self._check_client_connected()
        await self._client.cancel_task(self._task_id)

    async def delete(self) -> None:
        """Delete this task and all associated data from the server.

        Deletion is discretionary - servers may reject delete requests.
        After successful deletion, calling result() or status() will raise errors.

        Note: If server executed immediately (graceful degradation), this is a no-op
        as there's no server-side task to delete.
        """
        if self._is_immediate:
            # No server-side task to delete
            return
        self._check_client_connected()
        await self._client.delete_task(self._task_id)

    def __await__(self):
        """Allow 'await task' to get result."""
        return self.result().__await__()


class ToolTask(Task[CallToolResult]):
    """
    Represents a tool call that may execute in background or immediately.

    Provides a uniform API whether the server accepts background execution
    or executes synchronously (graceful degradation per SEP-1686).

    Usage:
        task = await client.call_tool_as_task("analyze", args)

        # Check status
        status = await task.status()

        # Wait for completion
        await task.wait()

        # Get result (waits if needed)
        result = await task.result()  # Returns CallToolResult

        # Or just await the task directly
        result = await task
    """

    def __init__(
        self,
        client: "Client",
        task_id: str,
        tool_name: str,
        immediate_result: CallToolResult | None = None,
    ):
        """
        Create a ToolTask wrapper.

        Args:
            client: The FastMCP client
            task_id: The task identifier
            tool_name: Name of the tool being executed
            immediate_result: If server executed synchronously, the immediate result
        """
        super().__init__(client, task_id, immediate_result)
        self._tool_name = tool_name

    async def result(self) -> CallToolResult:
        """Wait for and return the tool result.

        If server executed immediately, returns the immediate result.
        Otherwise waits for background task to complete and retrieves result.

        Returns:
            CallToolResult: The parsed tool result (same as call_tool returns)
        """
        # Check cache first
        if self._cached_result is not None:
            return self._cached_result

        if self._is_immediate:
            assert self._immediate_result is not None  # Type narrowing
            result = self._immediate_result
        else:
            # Check client connected
            self._check_client_connected()

            # Wait for completion
            await self._client.wait_for_task(self._task_id)

            # Get the raw result (could be ToolResult or CallToolResult)
            raw_result = await self._client.get_task_result(self._task_id)

            # If it's a ToolResult (from shim), convert to mcp.types.CallToolResult then parse
            if hasattr(raw_result, "content") and hasattr(
                raw_result, "structured_content"
            ):
                # It's a ToolResult - convert to MCP type
                mcp_result = mcp.types.CallToolResult(
                    content=raw_result.content,
                    structuredContent=raw_result.structured_content,  # type: ignore[arg-type]
                    _meta=raw_result.meta,
                )
                # Parse it the same way call_tool does (adds .data field)
                result = await self._client._parse_call_tool_result(
                    self._tool_name, mcp_result, raise_on_error=True
                )
            elif isinstance(raw_result, mcp.types.CallToolResult):
                # Already a CallToolResult from MCP protocol - parse it
                result = await self._client._parse_call_tool_result(
                    self._tool_name, raw_result, raise_on_error=True
                )
            else:
                # Unknown type - just return it
                result = raw_result  # type: ignore[assignment]

        # Cache before returning
        self._cached_result = result
        return result


class PromptTask(Task[mcp.types.GetPromptResult]):
    """
    Represents a prompt call that may execute in background or immediately.

    Provides a uniform API whether the server accepts background execution
    or executes synchronously (graceful degradation per SEP-1686).

    Usage:
        task = await client.get_prompt_as_task("analyze", args)
        result = await task  # Returns GetPromptResult
    """

    def __init__(
        self,
        client: "Client",
        task_id: str,
        prompt_name: str,
        immediate_result: mcp.types.GetPromptResult | None = None,
    ):
        """
        Create a PromptTask wrapper.

        Args:
            client: The FastMCP client
            task_id: The task identifier
            prompt_name: Name of the prompt being executed
            immediate_result: If server executed synchronously, the immediate result
        """
        super().__init__(client, task_id, immediate_result)
        self._prompt_name = prompt_name

    async def result(self) -> mcp.types.GetPromptResult:
        """Wait for and return the prompt result.

        If server executed immediately, returns the immediate result.
        Otherwise waits for background task to complete and retrieves result.

        Returns:
            GetPromptResult: The prompt result with messages and description
        """
        # Check cache first
        if self._cached_result is not None:
            return self._cached_result

        if self._is_immediate:
            assert self._immediate_result is not None
            result = self._immediate_result
        else:
            # Check client connected
            self._check_client_connected()

            # Wait for completion
            await self._client.wait_for_task(self._task_id)

            # Get the raw MCP result
            mcp_result = await self._client.get_task_result(self._task_id)

            # Parse as GetPromptResult
            result = mcp.types.GetPromptResult.model_validate(mcp_result)

        # Cache before returning
        self._cached_result = result
        return result


class ResourceTask(
    Task[list[mcp.types.TextResourceContents | mcp.types.BlobResourceContents]]
):
    """
    Represents a resource read that may execute in background or immediately.

    Provides a uniform API whether the server accepts background execution
    or executes synchronously (graceful degradation per SEP-1686).

    Usage:
        task = await client.read_resource_as_task("file://data.txt")
        contents = await task  # Returns list[ReadResourceContents]
    """

    def __init__(
        self,
        client: "Client",
        task_id: str,
        uri: str,
        immediate_result: list[
            mcp.types.TextResourceContents | mcp.types.BlobResourceContents
        ]
        | None = None,
    ):
        """
        Create a ResourceTask wrapper.

        Args:
            client: The FastMCP client
            task_id: The task identifier
            uri: URI of the resource being read
            immediate_result: If server executed synchronously, the immediate result
        """
        super().__init__(client, task_id, immediate_result)
        self._uri = uri

    async def result(
        self,
    ) -> list[mcp.types.TextResourceContents | mcp.types.BlobResourceContents]:
        """Wait for and return the resource contents.

        If server executed immediately, returns the immediate result.
        Otherwise waits for background task to complete and retrieves result.

        Returns:
            list[ReadResourceContents]: The resource contents
        """
        # Check cache first
        if self._cached_result is not None:
            return self._cached_result

        if self._is_immediate:
            assert self._immediate_result is not None
            result = self._immediate_result
        else:
            # Check client connected
            self._check_client_connected()

            # Wait for completion
            await self._client.wait_for_task(self._task_id)

            # Get the raw MCP result
            mcp_result = await self._client.get_task_result(self._task_id)

            # Parse as ReadResourceResult or extract contents
            if isinstance(mcp_result, mcp.types.ReadResourceResult):
                # Already parsed by TasksResponse - extract contents
                result = list(mcp_result.contents)
            elif isinstance(mcp_result, dict) and "contents" in mcp_result:
                # Dict format - parse each content item
                parsed_contents = []
                for item in mcp_result["contents"]:
                    if isinstance(item, dict):
                        if "blob" in item:
                            parsed_contents.append(
                                mcp.types.BlobResourceContents.model_validate(item)
                            )
                        else:
                            parsed_contents.append(
                                mcp.types.TextResourceContents.model_validate(item)
                            )
                    else:
                        parsed_contents.append(item)
                result = parsed_contents
            else:
                # Fallback - might be the list directly
                result = mcp_result if isinstance(mcp_result, list) else [mcp_result]

        # Cache before returning
        self._cached_result = result
        return result
