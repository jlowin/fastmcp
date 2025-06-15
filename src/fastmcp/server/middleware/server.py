import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from mcp import ServerNotification, ServerSession
from mcp.server.lowlevel.server import LifespanResultT, RequestT, Server, request_ctx
from mcp.shared.context import RequestContext
from mcp.shared.exceptions import McpError
from mcp.shared.message import ServerMessageMetadata
from mcp.shared.session import (
    RequestId,
    SendRequestT,
)
from mcp.types import METHOD_NOT_FOUND, ErrorData

from .mcp_middleware import MCPMiddleware

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class MiddlewareServer(Server[LifespanResultT, RequestT]):
    def __init__(self, *args, middleware: list[MCPMiddleware] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._middleware: list[MCPMiddleware] = middleware or []

    def add_middleware(self, middleware: MCPMiddleware) -> None:
        """Add middleware to the stack."""
        self._middleware.append(middleware)

    async def _apply_middleware(
        self, message: Any, call_next: Callable[[Any], Awaitable[R]]
    ) -> R:
        """Apply middleware chain to a message."""
        # Build the chain from right to left
        next_func = call_next
        for mw in reversed(self._middleware):
            next_func = self._make_middleware_wrapper(mw, next_func)
        return await next_func(message)

    @staticmethod
    def _make_middleware_wrapper(
        middleware: MCPMiddleware, next_func: Callable[[Any], Awaitable[R]]
    ) -> Callable[[Any], Awaitable[R]]:
        """Create a wrapper that applies a single middleware."""

        async def wrapper(message: Any) -> R:
            return await middleware(message, next_func)

        return wrapper

    async def _handle_request(
        self, message, req, session, lifespan_context, raise_exceptions
    ):
        """Handle requests with middleware."""
        logger.info("Processing request of type %s", type(req).__name__)

        # Create a handler that executes the original logic
        async def execute_request(req_to_handle):
            handler = self.request_handlers.get(type(req_to_handle))

            if not handler:
                logger.debug("No handler for %s", type(req_to_handle).__name__)
                return ErrorData(code=METHOD_NOT_FOUND, message="Method not found")

            try:
                # Extract request context from message metadata
                request_data = None
                if message.message_metadata is not None and isinstance(
                    message.message_metadata, ServerMessageMetadata
                ):
                    request_data = message.message_metadata.request_context

                # Set request context before calling handler
                token = request_ctx.set(
                    RequestContext(
                        message.request_id,
                        message.request_meta,
                        session,
                        lifespan_context,
                        request=request_data,
                    )
                )

                # Wrap session methods for this request
                self._wrap_session_methods(session)

                return await handler(req_to_handle)
            except McpError as err:
                return err.error
            except Exception as err:
                if raise_exceptions:
                    raise
                return ErrorData(code=0, message=str(err), data=None)
            finally:
                if token:
                    request_ctx.reset(token)

        # Apply middleware if present
        if self._middleware:
            response = await self._apply_middleware(req, execute_request)
        else:
            response = await execute_request(req)

        # Send response
        await message.respond(response)
        logger.debug("Response sent")

    async def _handle_notification(self, notify: Any):
        """Handle notifications with middleware."""
        logger.debug("Processing notification of type %s", type(notify).__name__)

        # Create a handler that executes the original logic
        async def execute_notification(notif):
            handler = self.notification_handlers.get(type(notif))
            if handler:
                await handler(notif)
            else:
                logger.debug("Unhandled notification: %s", type(notif).__name__)

        # Apply middleware if present
        if self._middleware:
            await self._apply_middleware(notify, execute_notification)
        else:
            await execute_notification(notify)

    def _wrap_session_methods(self, session: ServerSession):
        """Wrap session methods to intercept server->client communication."""
        # Only wrap if not already wrapped
        if hasattr(session.send_notification, "_middleware_wrapped"):
            return

        original_send_notification = session.send_notification
        original_send_request = session.send_request

        async def wrapped_send_notification(
            notification: ServerNotification,
            related_request_id: RequestId | None = None,
        ):
            # Apply middleware to outgoing notifications
            async def send_it(notif):
                return await original_send_notification(notif, related_request_id)

            if self._middleware:
                return await self._apply_middleware(notification, send_it)
            return await send_it(notification)

        async def wrapped_send_request(request: SendRequestT, *args, **kwargs):
            # Apply middleware to outgoing requests
            async def send_it(req):
                return await original_send_request(req, *args, **kwargs)

            if self._middleware:
                return await self._apply_middleware(request, send_it)
            return await send_it(request)

        # Mark as wrapped to avoid double-wrapping
        wrapped_send_notification._middleware_wrapped = True
        wrapped_send_request._middleware_wrapped = True

        session.send_notification = wrapped_send_notification
        session.send_request = wrapped_send_request
