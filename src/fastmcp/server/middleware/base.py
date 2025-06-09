import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, Protocol, TypeVar, runtime_checkable

import mcp.types as types
from mcp.shared.session import RequestResponder

logger = logging.getLogger(__name__)

# Type vars for better typing
RequestT = TypeVar("RequestT")
NotificationT = TypeVar("NotificationT")

MessageT = TypeVar(
    "MessageT",
    types.Request,
    types.ServerNotification,
    types.Notification,
    RequestResponder,
)

ServerResultT = TypeVar(
    "ServerResultT",
    bound=types.EmptyResult
    | types.InitializeResult
    | types.CompleteResult
    | types.GetPromptResult
    | types.ListPromptsResult
    | types.ListResourcesResult
    | types.ListResourceTemplatesResult
    | types.ReadResourceResult
    | types.CallToolResult
    | types.ListToolsResult,
)


@runtime_checkable
class ServerResultProtocol(Protocol[ServerResultT]):
    root: ServerResultT


class MCPMiddlewareProtocol(Protocol):
    async def __call__(
        self, message: Any, call_next: Callable[[Any], Awaitable[Any]]
    ) -> Any: ...


class MCPMiddleware:
    """
    Base class for MCP middleware with typed hooks.

    Note: Initialize requests are not handled by this middleware, as they are sent before
    the server is initialized. Instead, the `on_initialize` hook is called with a
    `InitializedNotification` once the server is initialized.
    """

    async def __call__(
        self,
        message: MessageT,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        return await self.on_message(
            message, partial(self._dispatch_message_type, call_next=call_next)
        )

    async def _dispatch_message_type(
        self, message: Any, call_next: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """Main dispatcher that routes to appropriate hooks."""

        # The client is requesting a response from the server
        if isinstance(message, types.Request):
            return await self.on_client_request(
                message, partial(self._dispatch_request_type, call_next=call_next)
            )
        # The client is sending a notification to the server
        elif isinstance(message, types.Notification):
            return await self.on_client_notification(
                message, partial(self._dispatch_notification_type, call_next=call_next)
            )
        # The server is sending a notification to the client
        elif isinstance(message, types.ServerNotification):
            return await self.on_server_notification(
                message.root,
                partial(self._dispatch_notification_type, call_next=call_next),
            )
        # The server is requesting a response from the client
        elif isinstance(message, types.ServerRequest):
            return await self.on_server_request(
                message.root, partial(self._dispatch_request_type, call_next=call_next)
            )
        else:
            # remove this once we know all possible types
            raise ValueError(f"Unknown message type: {type(message)}")
            return await call_next(message)

    async def _dispatch_request_type(
        self,
        request: Any,
        call_next: Callable[[types.Request], Awaitable[ServerResultProtocol[Any]]],
    ) -> ServerResultProtocol[Any]:
        """Handle a specific request type."""
        if isinstance(request, types.ListToolsRequest):
            return await self.on_list_tools_request(request, call_next)
        elif isinstance(request, types.CallToolRequest):
            return await self.on_call_tool_request(request, call_next)
        elif isinstance(request, types.ListResourcesRequest):
            return await self.on_list_resources_request(request, call_next)
        elif isinstance(request, types.ListResourceTemplatesRequest):
            return await self.on_list_resource_templates_request(request, call_next)
        elif isinstance(request, types.ReadResourceRequest):
            return await self.on_read_resource_request(request, call_next)
        elif isinstance(request, types.ListPromptsRequest):
            return await self.on_list_prompts_request(request, call_next)
        elif isinstance(request, types.GetPromptRequest):
            return await self.on_get_prompt_request(request, call_next)
        elif isinstance(request, types.CompleteRequest):
            return await self.on_complete_request(request, call_next)
        else:
            return await call_next(request)

    async def _dispatch_notification_type(
        self,
        notification: Any,
        call_next: Callable[[types.Notification], Awaitable[None]],
    ) -> Any:
        """Handle a specific notification type."""
        if isinstance(notification, types.InitializedNotification):
            return await self.on_initialize_notification(notification, call_next)
        elif isinstance(notification, types.ProgressNotification):
            return await self.on_progress_notification(notification, call_next)
        elif isinstance(notification, types.LoggingMessageNotification):
            return await self.on_logging_message_notification(notification, call_next)
        elif isinstance(notification, types.ResourceUpdatedNotification):
            return await self.on_resource_updated_notification(notification, call_next)
        elif isinstance(notification, types.ToolListChangedNotification):
            return await self.on_tool_list_changed_notification(notification, call_next)
        elif isinstance(notification, types.ResourceListChangedNotification):
            return await self.on_resource_list_changed_notification(
                notification, call_next
            )
        elif isinstance(notification, types.PromptListChangedNotification):
            return await self.on_prompt_list_changed_notification(
                notification, call_next
            )
        else:
            return await call_next(notification)

    # ---
    #
    #
    # Request hooks - these return ServerResult
    #
    #
    # ---

    async def on_list_tools_request(
        self,
        request: types.ListToolsRequest,
        call_next: Callable[
            [types.ListToolsRequest],
            Awaitable[ServerResultProtocol[types.ListToolsResult]],
        ],
    ) -> ServerResultProtocol[types.ListToolsResult]:
        """Hook for list_tools requests."""
        return await call_next(request)

    async def on_call_tool_request(
        self,
        request: types.CallToolRequest,
        call_next: Callable[
            [types.CallToolRequest],
            Awaitable[ServerResultProtocol[types.CallToolResult]],
        ],
    ) -> ServerResultProtocol[types.CallToolResult]:
        """Hook for call_tool requests."""
        return await call_next(request)

    async def on_list_resources_request(
        self,
        request: types.ListResourcesRequest,
        call_next: Callable[
            [types.ListResourcesRequest],
            Awaitable[ServerResultProtocol[types.ListResourcesResult]],
        ],
    ) -> ServerResultProtocol[types.ListResourcesResult]:
        """Hook for list_resources requests."""
        return await call_next(request)

    async def on_list_resource_templates_request(
        self,
        request: types.ListResourceTemplatesRequest,
        call_next: Callable[
            [types.ListResourceTemplatesRequest],
            Awaitable[ServerResultProtocol[types.ListResourceTemplatesResult]],
        ],
    ) -> ServerResultProtocol[types.ListResourceTemplatesResult]:
        """Hook for list_resource_templates requests."""
        return await call_next(request)

    async def on_read_resource_request(
        self,
        request: types.ReadResourceRequest,
        call_next: Callable[
            [types.ReadResourceRequest],
            Awaitable[ServerResultProtocol[types.ReadResourceResult]],
        ],
    ) -> ServerResultProtocol[types.ReadResourceResult]:
        """Hook for read_resource requests."""
        return await call_next(request)

    async def on_list_prompts_request(
        self,
        request: types.ListPromptsRequest,
        call_next: Callable[
            [types.ListPromptsRequest],
            Awaitable[ServerResultProtocol[types.ListPromptsResult]],
        ],
    ) -> ServerResultProtocol[types.ListPromptsResult]:
        """Hook for list_prompts requests."""
        return await call_next(request)

    async def on_get_prompt_request(
        self,
        request: types.GetPromptRequest,
        call_next: Callable[
            [types.GetPromptRequest],
            Awaitable[ServerResultProtocol[types.GetPromptResult]],
        ],
    ) -> ServerResultProtocol[types.GetPromptResult]:
        """Hook for get_prompt requests."""
        return await call_next(request)

    async def on_complete_request(
        self,
        request: types.CompleteRequest,
        call_next: Callable[
            [types.CompleteRequest],
            Awaitable[ServerResultProtocol[types.CompleteResult]],
        ],
    ) -> ServerResultProtocol[types.CompleteResult]:
        """Hook for completion requests."""
        return await call_next(request)

    # ---
    #
    #
    # Notification hooks - these return None
    #
    #
    # ---

    async def on_initialize_notification(
        self,
        notification: types.InitializedNotification,
        call_next: Callable[[types.InitializedNotification], Awaitable[None]],
    ) -> None:
        """Hook for initialize notifications."""
        return await call_next(notification)

    async def on_progress_notification(
        self,
        notification: types.ProgressNotification,
        call_next: Callable[[types.ProgressNotification], Awaitable[None]],
    ) -> None:
        """Hook for progress notifications."""
        await call_next(notification)

    async def on_logging_message_notification(
        self,
        notification: types.LoggingMessageNotification,
        call_next: Callable[[types.LoggingMessageNotification], Awaitable[None]],
    ) -> None:
        """Hook for logging notifications."""
        await call_next(notification)

    async def on_resource_updated_notification(
        self,
        notification: types.ResourceUpdatedNotification,
        call_next: Callable[[types.ResourceUpdatedNotification], Awaitable[None]],
    ) -> None:
        """Hook for resource updated notifications."""
        await call_next(notification)

    async def on_tool_list_changed_notification(
        self,
        notification: types.ToolListChangedNotification,
        call_next: Callable[[types.ToolListChangedNotification], Awaitable[None]],
    ) -> None:
        """Hook for tool list changed notifications."""
        await call_next(notification)

    async def on_resource_list_changed_notification(
        self,
        notification: types.ResourceListChangedNotification,
        call_next: Callable[[types.ResourceListChangedNotification], Awaitable[None]],
    ) -> None:
        """Hook for resource list changed notifications."""
        await call_next(notification)

    async def on_prompt_list_changed_notification(
        self,
        notification: types.PromptListChangedNotification,
        call_next: Callable[[types.PromptListChangedNotification], Awaitable[None]],
    ) -> None:
        """Hook for prompt list changed notifications."""
        await call_next(notification)

    # Convenience hooks that span multiple message types
    async def on_message(
        self,
        message: MessageT,
        call_next: Callable[[MessageT], Awaitable[Any]],
    ) -> Any:
        """
        Hook called for EVERY message (requests and notifications) before any other processing.
        """
        return await call_next(message)

    async def on_client_request(
        self,
        request: types.Request,
        call_next: Callable[[Any], Awaitable[ServerResultProtocol[Any]]],
    ) -> ServerResultProtocol[Any]:
        """
        Hook called for any request type before specific hooks.

        Note that this is called for ALL MCP requests before any specific hooks.

        Also note that an MCP "request" is not the same as an HTTP request, and
        does not include notifications. Implement `on_message` to handle every
        incoming message.
        """
        return await call_next(request)

    async def on_client_notification(
        self,
        notification: types.Notification,
        call_next: Callable[[Any], Awaitable[None]],
    ) -> None:
        """
        Hook called for any notification type before specific hooks.

        Note that this is called for ALL MCP notifications before any specific hooks.
        """
        await call_next(notification)

    async def on_server_notification(
        self,
        notification: types.Notification,
        call_next: Callable[[types.Notification], Awaitable[None]],
    ) -> None:
        """Hook for server notifications."""
        await call_next(notification)

    async def on_server_request(
        self,
        request: types.Request,
        call_next: Callable[[types.Request], Awaitable[ServerResultProtocol[Any]]],
    ) -> ServerResultProtocol[Any]:
        """Hook for server requests."""
        return await call_next(request)
