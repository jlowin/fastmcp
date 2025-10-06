from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastmcp.contrib.server_lifespan import FastMCP
from fastmcp.server.context import Context
from fastmcp.utilities.logging import get_logger

logger = get_logger(name=__name__)


class FakeDB:
    _id: int

    def __init__(self):
        self._id = 0

    def get(self) -> int:
        return self._id

    def set(self, number: int) -> None:
        self._id = number


class ServerContext:
    db: FakeDB

    def __init__(self):
        self.db = FakeDB()


@asynccontextmanager
async def initialize_once(fastmcp: FastMCP) -> AsyncIterator[ServerContext]:
    logger.info("Initializing the Server Lifespan")
    yield ServerContext()
    logger.info("Done initializing the server lifespan.")


mcp = FastMCP(lifespan=initialize_once)


@mcp.tool
def get_value_from_db(ctx: Context):
    server_context: ServerContext = cast(
        "ServerContext", ctx.request_context.lifespan_context
    )

    return server_context.db.get()


@mcp.tool
def increment_value_in_db(ctx: Context, new_value: int):
    server_context: ServerContext = cast(
        "ServerContext", ctx.request_context.lifespan_context
    )

    return server_context.db.set(new_value)


mcp.run(transport="streamable-http")
