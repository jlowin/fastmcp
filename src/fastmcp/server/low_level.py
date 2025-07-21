from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

import anyio
import mcp.types as types
from mcp.server.lowlevel.server import (
    LifespanResultT,
    NotificationOptions,
    RequestT,
)
from mcp.server.lowlevel.server import (
    Server as _Server,
)
from mcp.server.models import InitializationOptions
from mcp.server.session import ServerSession
from mcp.shared.session import RequestResponder

if TYPE_CHECKING:
    from fastmcp.server.middleware.middleware import MiddlewareContext
    from fastmcp.server.server import FastMCP


class MiddlewareExposedServerSession(ServerSession):
    """ServerSession that routes initialization requests through FastMCP middleware."""

    def __init__(self, fastmcp_server: "FastMCP", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fastmcp_server = fastmcp_server

    async def _received_request(
        self, responder: RequestResponder[types.ClientRequest, types.ServerResult]
    ):
        # Check if this is an initialization request and if middleware should handle it
        if (
            isinstance(responder.request.root, types.InitializeRequest)
            and self.fastmcp_server
            and hasattr(self.fastmcp_server, "_apply_middleware")
        ):
            # Import here to avoid circular imports
            from fastmcp.server.middleware.middleware import MiddlewareContext

            # HACK: Pass session object directly to middleware context for proof-of-concept
            context = MiddlewareContext(
                message=responder.request.root.params,
                method="initialize",
                type="request",
                source="client",
                session=self,  # Pass session so middleware can store data on it
            )

            # Create a continuation that calls the original initialization handler
            async def call_original_handler(
                ctx: "MiddlewareContext",
            ) -> types.InitializeResult:
                # Call the original handler by continuing to the parent implementation
                await super(MiddlewareExposedServerSession, self)._received_request(
                    responder
                )
                # The response will be handled by the parent, we just need to extract the result
                # This is a bit tricky since the parent handles the response internally
                # For now, we'll call the parent and assume it handles the response correctly
                return None  # Parent handles the actual response

            # Apply middleware chain, but still let parent handle the actual response
            try:
                await self.fastmcp_server._apply_middleware(
                    context, call_original_handler
                )
            except Exception:
                # If middleware fails, fall back to original handling
                await super()._received_request(responder)
        else:
            # For non-initialization requests or when no middleware, use original handling
            await super()._received_request(responder)


class LowLevelServer(_Server[LifespanResultT, RequestT]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FastMCP servers support notifications for all components
        self.notification_options = NotificationOptions(
            prompts_changed=True,
            resources_changed=True,
            tools_changed=True,
        )
        # Reference to FastMCP server for middleware integration
        self.fastmcp_server: FastMCP | None = None

    def create_initialization_options(
        self,
        notification_options: NotificationOptions | None = None,
        experimental_capabilities: dict[str, dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> InitializationOptions:
        # ensure we use the FastMCP notification options
        if notification_options is None:
            notification_options = self.notification_options
        return super().create_initialization_options(
            notification_options=notification_options,
            experimental_capabilities=experimental_capabilities,
            **kwargs,
        )

    async def run(
        self,
        read_stream,
        write_stream,
        initialization_options,
        raise_exceptions=False,
        stateless=False,
    ):
        """Override run to use MiddlewareExposedServerSession when fastmcp_server is available."""
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(self.lifespan(self))

            # Use MiddlewareExposedServerSession if we have a FastMCP server, otherwise use default
            if self.fastmcp_server:
                session = await stack.enter_async_context(
                    MiddlewareExposedServerSession(
                        self.fastmcp_server,
                        read_stream,
                        write_stream,
                        initialization_options,
                        stateless=stateless,
                    )
                )
            else:
                session = await stack.enter_async_context(
                    ServerSession(
                        read_stream,
                        write_stream,
                        initialization_options,
                        stateless=stateless,
                    )
                )

            async with anyio.create_task_group() as tg:
                async for message in session.incoming_messages:
                    tg.start_soon(
                        self._handle_message,
                        message,
                        session,
                        lifespan_context,
                        raise_exceptions,
                    )
