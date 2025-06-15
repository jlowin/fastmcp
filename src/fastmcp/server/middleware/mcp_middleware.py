from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

import mcp.types as types
from mcp.server.session import ServerSession

logger = logging.getLogger(__name__)


T = TypeVar("T")
R = TypeVar("R")

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


@runtime_checkable
class MiddlewareHandler(Protocol[T, R]):
    """
    A protocol for middleware handlers.
    """

    def __call__(
        self,
        message: T,
        context: MiddlewareContext,
        call_next: Callable[[T], Awaitable[R]],
    ) -> Awaitable[R]: ...


@dataclass(kw_only=True, frozen=True)
class MiddlewareContext:
    """
    Context passed to all middleware hooks.

    Contains metadata about the message being processed.
    """

    # the raw message
    message: Any
    # was the request initiated by the client or the server?
    source: Literal["client", "server"] = "client"
    # the session object
    session: ServerSession | None = None
    # the request id
    request_id: str | None = None
    # timestamp: datetime
    # correlation_id: str
    # context: Context


class MCPMiddleware:
    """
    Base class for MCP middleware with context pattern.

    All hooks receive two arguments:
    1. The message being processed (specific type)
    2. A context object with metadata (can be ignored with **kwargs)
    """

    async def __call__(
        self,
        message: Any,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Main entry point that orchestrates the pipeline."""

        context = MiddlewareContext(
            message=message,
            session=None,
            request_id=None,
        )

        # Process the message
        return await self._process_message(
            message, context=context, call_next=call_next
        )

    def _create_handler(
        self,
        method: MiddlewareHandler[T, R],
        context: MiddlewareContext,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Callable[[T], Awaitable[R]]:
        """
        Create a handler function with a single argument for a given method,
        context, and call_next function.
        """

        async def handler(message: T) -> R:
            return await method(message, context=context, call_next=call_next)

        return handler

    async def _process_message(
        self,
        message: Any,
        context: MiddlewareContext,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Process message through appropriate hooks."""

        # start with the next handler
        handler = call_next

        # server-initiated requests and notifications are wrapped in a
        # ServerRequest or ServerNotification RootModel. We unwrap them here,
        # but ensure call_next gets the original wrapped message.
        match message:
            case types.ServerNotification(root=inner_message):
                # Create a handler that passes the *original* message to call_next
                async def wrapped_handler(inner_message):
                    return await call_next(message)

                # Recursively process the inner message with the wrapped handler
                return await self._process_message(
                    inner_message,
                    context=replace(context, source="server"),
                    call_next=wrapped_handler,
                )

            case types.ServerRequest(root=inner_message):
                # Create a handler that passes the *original* message to call_next
                async def wrapped_handler(inner_message):
                    return await call_next(message)

                # Recursively process the inner message with the wrapped handler
                return await self._process_message(
                    inner_message,
                    context=replace(context, source="server"),
                    call_next=wrapped_handler,
                )

        # next, add the type-specific handler to the chain
        match message:
            # --- Requests ---

            case types.ListToolsRequest():
                handler = self._create_handler(
                    self.on_list_tools_request, context, call_next=handler
                )

            case types.CallToolRequest():
                handler = self._create_handler(
                    self.on_call_tool_request, context, call_next=handler
                )
            case types.ListResourcesRequest():
                handler = self._create_handler(
                    self.on_list_resources_request, context, call_next=handler
                )
            case types.ListResourceTemplatesRequest():
                handler = self._create_handler(
                    self.on_list_resource_templates_request,
                    context,
                    call_next=handler,
                )
            case types.ReadResourceRequest():
                handler = self._create_handler(
                    self.on_read_resource_request, context, call_next=handler
                )
            case types.ListPromptsRequest():
                handler = self._create_handler(
                    self.on_list_prompts_request, context, call_next=handler
                )
            case types.GetPromptRequest():
                handler = self._create_handler(
                    self.on_get_prompt_request, context, call_next=handler
                )
            case types.CompleteRequest():
                handler = self._create_handler(
                    self.on_complete_request, context, call_next=handler
                )
            case types.PingRequest():
                handler = self._create_handler(
                    self.on_ping_request, context, call_next=handler
                )
            case types.CreateMessageRequest():
                handler = self._create_handler(
                    self.on_create_message_request, context, call_next=handler
                )
            case types.ListRootsRequest():
                handler = self._create_handler(
                    self.on_list_roots_request, context, call_next=handler
                )

            # --- Notifications ---

            case types.InitializedNotification():
                handler = self._create_handler(
                    self.on_initialize_notification, context, call_next=handler
                )
            case types.ProgressNotification():
                handler = self._create_handler(
                    self.on_progress_notification, context, call_next=handler
                )
            case types.LoggingMessageNotification():
                handler = self._create_handler(
                    self.on_logging_message_notification, context, call_next=handler
                )
            case types.ResourceUpdatedNotification():
                handler = self._create_handler(
                    self.on_resource_updated_notification, context, call_next=handler
                )
            case types.ToolListChangedNotification():
                handler = self._create_handler(
                    self.on_tool_list_changed_notification, context, call_next=handler
                )
            case types.ResourceListChangedNotification():
                handler = self._create_handler(
                    self.on_resource_list_changed_notification,
                    context,
                    call_next=handler,
                )
            case types.PromptListChangedNotification():
                handler = self._create_handler(
                    self.on_prompt_list_changed_notification,
                    context,
                    call_next=handler,
                )
            case types.RootsListChangedNotification():
                handler = self._create_handler(
                    self.on_roots_list_changed_notification,
                    context,
                    call_next=handler,
                )
            case types.CancelledNotification():
                handler = self._create_handler(
                    self.on_cancelled_notification, context, call_next=handler
                )

        # next, add the request and notification hooks
        match message:
            case types.Request():
                handler = self._create_handler(
                    self.on_request, context, call_next=handler
                )
            case types.Notification():
                handler = self._create_handler(
                    self.on_notification, context, call_next=handler
                )

        # finally, add the general message hook
        handler = self._create_handler(self.on_message, context, call_next=handler)

        # process the message through the handler chain
        return await handler(message)

    # ---
    # Request hooks
    # ---

    async def on_list_tools_request(
        self,
        message: types.ListToolsRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ListToolsRequest],
            Awaitable[ServerResultProtocol[types.ListToolsResult]],
        ],
    ) -> ServerResultProtocol[types.ListToolsResult]:
        """Process list_tools request."""
        return await call_next(message)

    async def on_call_tool_request(
        self,
        message: types.CallToolRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.CallToolRequest],
            Awaitable[ServerResultProtocol[types.CallToolResult]],
        ],
    ) -> ServerResultProtocol[types.CallToolResult]:
        """Process call_tool request."""
        return await call_next(message)

    async def on_list_resources_request(
        self,
        message: types.ListResourcesRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ListResourcesRequest],
            Awaitable[ServerResultProtocol[types.ListResourcesResult]],
        ],
    ) -> ServerResultProtocol[types.ListResourcesResult]:
        """Process list_resources request."""
        return await call_next(message)

    async def on_list_resource_templates_request(
        self,
        message: types.ListResourceTemplatesRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ListResourceTemplatesRequest],
            Awaitable[ServerResultProtocol[types.ListResourceTemplatesResult]],
        ],
    ) -> ServerResultProtocol[types.ListResourceTemplatesResult]:
        """Process list_resource_templates request."""
        return await call_next(message)

    async def on_read_resource_request(
        self,
        message: types.ReadResourceRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ReadResourceRequest],
            Awaitable[ServerResultProtocol[types.ReadResourceResult]],
        ],
    ) -> ServerResultProtocol[types.ReadResourceResult]:
        """Process read_resource request."""
        return await call_next(message)

    async def on_list_prompts_request(
        self,
        message: types.ListPromptsRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ListPromptsRequest],
            Awaitable[ServerResultProtocol[types.ListPromptsResult]],
        ],
    ) -> ServerResultProtocol[types.ListPromptsResult]:
        """Process list_prompts request."""
        return await call_next(message)

    async def on_get_prompt_request(
        self,
        message: types.GetPromptRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.GetPromptRequest],
            Awaitable[ServerResultProtocol[types.GetPromptResult]],
        ],
    ) -> ServerResultProtocol[types.GetPromptResult]:
        """Process get_prompt request."""
        return await call_next(message)

    async def on_complete_request(
        self,
        message: types.CompleteRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.CompleteRequest],
            Awaitable[ServerResultProtocol[types.CompleteResult]],
        ],
    ) -> ServerResultProtocol[types.CompleteResult]:
        """Process completion request."""
        return await call_next(message)

    async def on_ping_request(
        self,
        message: types.PingRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.PingRequest],
            Awaitable[ServerResultProtocol[types.EmptyResult]],
        ],
    ) -> ServerResultProtocol[types.EmptyResult]:
        """Process ping request."""
        return await call_next(message)

    async def on_create_message_request(
        self,
        message: types.CreateMessageRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.CreateMessageRequest],
            Awaitable[types.CreateMessageResult],
        ],
    ) -> types.CreateMessageResult:
        """Process create_message request (used for sampling)"""
        return await call_next(message)

    async def on_list_roots_request(
        self,
        message: types.ListRootsRequest,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ListRootsRequest],
            Awaitable[types.ListRootsResult],
        ],
    ) -> types.ListRootsResult:
        """Process list_roots request."""
        return await call_next(message)

    # ---
    # Notification hooks
    # ---

    async def on_initialize_notification(
        self,
        message: types.InitializedNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.InitializedNotification],
            Awaitable[types.InitializedNotification],
        ],
    ) -> types.InitializedNotification:
        """Process initialize notification."""
        return await call_next(message)

    async def on_progress_notification(
        self,
        message: types.ProgressNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ProgressNotification],
            Awaitable[types.ProgressNotification],
        ],
    ) -> types.ProgressNotification:
        """Process progress notification."""
        return await call_next(message)

    async def on_logging_message_notification(
        self,
        message: types.LoggingMessageNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.LoggingMessageNotification],
            Awaitable[types.LoggingMessageNotification],
        ],
    ) -> types.LoggingMessageNotification:
        """Process logging notification."""
        return await call_next(message)

    async def on_resource_updated_notification(
        self,
        message: types.ResourceUpdatedNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ResourceUpdatedNotification],
            Awaitable[types.ResourceUpdatedNotification],
        ],
    ) -> types.ResourceUpdatedNotification:
        """Process resource updated notification."""
        return await call_next(message)

    async def on_tool_list_changed_notification(
        self,
        message: types.ToolListChangedNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ToolListChangedNotification],
            Awaitable[types.ToolListChangedNotification],
        ],
    ) -> types.ToolListChangedNotification:
        """Process tool list changed notification."""
        return await call_next(message)

    async def on_resource_list_changed_notification(
        self,
        message: types.ResourceListChangedNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.ResourceListChangedNotification],
            Awaitable[types.ResourceListChangedNotification],
        ],
    ) -> types.ResourceListChangedNotification:
        """Process resource list changed notification."""
        return await call_next(message)

    async def on_prompt_list_changed_notification(
        self,
        message: types.PromptListChangedNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.PromptListChangedNotification],
            Awaitable[types.PromptListChangedNotification],
        ],
    ) -> types.PromptListChangedNotification:
        """Process prompt list changed notification."""
        return await call_next(message)

    async def on_roots_list_changed_notification(
        self,
        message: types.RootsListChangedNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.RootsListChangedNotification],
            Awaitable[types.RootsListChangedNotification],
        ],
    ) -> types.RootsListChangedNotification:
        """Process roots list changed notification."""
        return await call_next(message)

    async def on_cancelled_notification(
        self,
        message: types.CancelledNotification,
        context: MiddlewareContext,
        call_next: Callable[
            [types.CancelledNotification],
            Awaitable[types.CancelledNotification],
        ],
    ) -> types.CancelledNotification:
        """Process cancelled notification."""
        return await call_next(message)

    # ---
    # General hooks
    # ---

    async def on_message(
        self,
        message: T,
        context: MiddlewareContext,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> R:
        """
        Hook called for EVERY message before any other processing.

        """
        return await call_next(message)

    async def on_request(
        self,
        message: types.Request,
        context: MiddlewareContext,
        call_next: Callable[[types.Request], Awaitable[types.Result[Any, Any]]],
    ) -> types.Result[Any, Any]:
        """
        Hook called for any request before specific hooks.

        """
        return await call_next(message)

    async def on_notification(
        self,
        message: types.Notification,
        context: MiddlewareContext,
        call_next: Callable[[types.Notification], Awaitable[types.Notification]],
    ) -> types.Notification:
        """
        Hook called for any notification before specific hooks.

        """
        return await call_next(message)
