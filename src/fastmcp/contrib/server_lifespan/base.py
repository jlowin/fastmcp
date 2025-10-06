"""
Server-level lifespan management for FastMCP.

This module provides a FastMCP subclass that manages server-wide resources
(like database connection pools) that should persist across multiple client sessions.

Note: This is experimental. The upstream MCP SDK's lifespan is designed to be
per-session. This contrib module works around that limitation for specific use cases.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any

from mcp.server.lowlevel.server import LifespanResultT
from typing_extensions import override

from fastmcp import FastMCP as _FastMCP


class FastMCP(_FastMCP[LifespanResultT]):
    """
    FastMCP subclass with server-wide lifespan management.

    Use this when you need to initialize expensive resources (like database
    connection pools) once when the server starts, rather than for each session.

    Example:
        ```python
        @asynccontextmanager
        async def server_lifespan(mcp):
            db_pool = await create_db_pool()
            try:
                yield db_pool
            finally:
                await db_pool.close()

        mcp = FastMCP("My Server", lifespan=lifespan)

        @mcp.tool()
        def query(ctx: Context) -> str:
            # ctx.request_context.lifespan_context is the db_pool
            return ctx.request_context.lifespan_context.query()

        mcp.run()
        ```

    Limitations:
        - Cannot use mount() or import_server() - raises NotImplementedError
        - Server lifespan is entered once per run() call, not per session
    """

    def __init__(self, *args: Any, **kwargs: Any):
        """
        Initialize with server-wide lifespan.

        Args:
            name: Server name
            server_lifespan: Async context manager for server-wide resources
            **kwargs: Other FastMCP arguments (except 'lifespan')
        """
        self._server_lifespan: (
            Callable[
                [FastMCP[LifespanResultT]],
                AbstractAsyncContextManager[LifespanResultT],
            ]
            | None
        ) = kwargs.pop("lifespan")
        self._server_lifespan_result: LifespanResultT | None = None
        self._server_lifespan_stack: AsyncExitStack | None = None

        # Create a per-session lifespan that returns the server's lifespan result
        @asynccontextmanager
        async def lifespan_proxy(
            app: _FastMCP[LifespanResultT],
        ) -> AsyncIterator[LifespanResultT]:
            # Return the already-initialized server context
            if self._server_lifespan_result is None:
                raise RuntimeError(
                    "Server lifespan not initialized. This should not happen."
                )
            yield self._server_lifespan_result

        super().__init__(*args, lifespan=lifespan_proxy, **kwargs)

    @override
    def mount(self, *args: Any, **kwargs: Any) -> None:
        """Mounting is not supported with ServerLifespanMixin."""
        raise NotImplementedError(
            "mount() is not supported with ServerLifespanMixin. "
            + "Server-wide lifespan management is incompatible with mounting."
        )

    @override
    async def import_server(self, *args, **kwargs) -> None:
        """Importing is not supported with ServerLifespanMixin."""
        raise NotImplementedError(
            "import_server() is not supported with ServerLifespanMixin. "
            + "Server-wide lifespan management is incompatible with importing."
        )

    async def _enter_server_lifespan(self):
        """Enter the server-wide lifespan context."""
        if self._server_lifespan_stack is not None:
            # Already entered
            return

        if self._server_lifespan is None:
            return

        self._server_lifespan_stack = AsyncExitStack()
        self._server_lifespan_result = (
            await self._server_lifespan_stack.enter_async_context(
                self._server_lifespan(self)
            )
        )

    async def _exit_server_lifespan(self):
        """Exit the server-wide lifespan context."""
        if self._server_lifespan_stack is not None:
            await self._server_lifespan_stack.aclose()
            self._server_lifespan_stack = None
            self._server_lifespan_result = None

    @override
    async def run_async(self, *args: Any, **kwargs: Any):
        """Run the server with server-wide lifespan management."""
        await self._enter_server_lifespan()
        try:
            await super().run_async(*args, **kwargs)
        finally:
            await self._exit_server_lifespan()
