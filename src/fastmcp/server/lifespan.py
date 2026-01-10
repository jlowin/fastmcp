"""Composable lifespans for FastMCP servers.

This module provides a `@lifespan` decorator for creating composable server lifespans
that can be combined using the `|` operator.

Example:
    ```python
    from fastmcp import FastMCP
    from fastmcp.server import lifespan

    @lifespan
    async def db_lifespan(server):
        conn = await connect_db()
        yield {"db": conn}
        await conn.close()

    @lifespan
    async def cache_lifespan(server):
        cache = await connect_cache()
        yield {"cache": cache}
        await cache.close()

    mcp = FastMCP("server", lifespan=db_lifespan | cache_lifespan)
    ```
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from fastmcp.server.server import FastMCP


LifespanFn = Callable[["FastMCP[Any]"], AsyncIterator[dict[str, Any]]]
LifespanContextManagerFn = Callable[
    ["FastMCP[Any]"], AbstractAsyncContextManager[dict[str, Any] | None]
]


class Lifespan:
    """Composable lifespan wrapper.

    Wraps an async generator function and enables composition via the `|` operator.
    The wrapped function should yield a dict that becomes part of the lifespan context.
    """

    def __init__(self, fn: LifespanFn) -> None:
        """Initialize a Lifespan wrapper.

        Args:
            fn: An async generator function that takes a FastMCP server and yields
                a dict for the lifespan context.
        """
        self._fn = fn

    @asynccontextmanager
    async def __call__(self, server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
        """Execute the lifespan as an async context manager.

        Args:
            server: The FastMCP server instance.

        Yields:
            The lifespan context dict.
        """
        async with asynccontextmanager(self._fn)(server) as result:
            yield result if result is not None else {}

    def __or__(
        self, other: Lifespan | LifespanFn | LifespanContextManagerFn
    ) -> ComposedLifespan:
        """Compose with another lifespan using the | operator.

        Args:
            other: Another Lifespan, async generator function, or context manager factory.

        Returns:
            A ComposedLifespan that runs both lifespans.
        """
        if not isinstance(other, Lifespan):
            # Check if it's an @asynccontextmanager decorated function
            if hasattr(other, "__wrapped__"):
                other = ContextManagerLifespan(cast(LifespanContextManagerFn, other))
            else:
                other = Lifespan(cast(LifespanFn, other))
        return ComposedLifespan(self, other)

    def __ror__(self, other: LifespanFn) -> ComposedLifespan:
        """Handle reverse composition when left operand is a function.

        Args:
            other: An async generator function or context manager factory.

        Returns:
            A ComposedLifespan that runs the function first, then this lifespan.
        """
        if callable(other):
            # Check if it's an @asynccontextmanager decorated function
            # These have a special attribute set by the decorator
            if hasattr(other, "__wrapped__"):
                return ComposedLifespan(
                    ContextManagerLifespan(cast(LifespanContextManagerFn, other)), self
                )
            return ComposedLifespan(Lifespan(other), self)
        raise TypeError(f"Cannot compose {type(other)} with Lifespan")


class ContextManagerLifespan(Lifespan):
    """Lifespan wrapper for already-wrapped context manager functions.

    Use this for functions already decorated with @asynccontextmanager.
    """

    _fn: LifespanContextManagerFn  # Override type for this subclass

    def __init__(self, fn: LifespanContextManagerFn) -> None:
        """Initialize with a context manager factory function."""
        self._fn = fn  # type: ignore[assignment]

    @asynccontextmanager
    async def __call__(self, server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
        """Execute the lifespan as an async context manager.

        Args:
            server: The FastMCP server instance.

        Yields:
            The lifespan context dict.
        """
        # self._fn is already a context manager factory, just call it
        async with self._fn(server) as result:
            yield result if result is not None else {}


class ComposedLifespan(Lifespan):
    """Two lifespans composed together.

    Enters the left lifespan first, then the right. Exits in reverse order.
    Results are shallow-merged into a single dict.
    """

    def __init__(self, left: Lifespan, right: Lifespan) -> None:
        """Initialize a composed lifespan.

        Args:
            left: The first lifespan to enter.
            right: The second lifespan to enter.
        """
        # Don't call super().__init__ since we override __call__
        self._left = left
        self._right = right

    @asynccontextmanager
    async def __call__(self, server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
        """Execute both lifespans, merging their results.

        Args:
            server: The FastMCP server instance.

        Yields:
            The merged lifespan context dict from both lifespans.
        """
        async with (
            self._left(server) as left_result,
            self._right(server) as right_result,
        ):
            yield {**left_result, **right_result}


def lifespan(fn: LifespanFn) -> Lifespan:
    """Decorator to create a composable lifespan.

    Use this decorator on an async generator function to make it composable
    with other lifespans using the `|` operator.

    Example:
        ```python
        @lifespan
        async def my_lifespan(server):
            # Setup
            resource = await create_resource()
            yield {"resource": resource}
            # Teardown
            await resource.close()

        mcp = FastMCP("server", lifespan=my_lifespan | other_lifespan)
        ```

    Args:
        fn: An async generator function that takes a FastMCP server and yields
            a dict for the lifespan context.

    Returns:
        A composable Lifespan wrapper.
    """
    return Lifespan(fn)
