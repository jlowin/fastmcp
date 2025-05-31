import pytest
from mcp.server.fastmcp import FastMCP as FastMCP1Server

from fastmcp.client.client import Client
from fastmcp.client.transports import FastMCPTransport
from fastmcp.server.context import Context
from fastmcp.server.server import FastMCP


@pytest.fixture
def fastmcp_server() -> FastMCP:
    mcp = FastMCP()

    @mcp.tool()
    def plus_one(x: int) -> int:
        return x + 1

    @mcp.tool()
    async def progress_tool(context: Context) -> int:
        for i in range(3):
            await context.report_progress(
                progress=i + 1,
                total=3,
                message=f"{(i + 1) / 3 * 100:.2f}% complete",
            )
        return 100

    return mcp


@pytest.fixture
def fastmcp1_server() -> FastMCP1Server:
    mcp = FastMCP1Server()

    @mcp.tool()
    def plus_one(x: int) -> int:
        return x + 1

    return mcp


async def test_stdio_ping(fastmcp_server: FastMCP):
    async with Client(transport=FastMCPTransport(fastmcp_server)) as client:
        assert await client.ping()


async def test_stdio_call(fastmcp_server: FastMCP):
    async with Client(transport=FastMCPTransport(fastmcp_server)) as client:
        result = await client.call_tool(name="plus_one", arguments={"x": 1})
        assert result[0].text == "2"  # type: ignore[attr-defined]


async def test_stdio_fastmcp_1_ping(fastmcp1_server: FastMCP1Server):
    async with Client(transport=FastMCPTransport(fastmcp1_server)) as client:
        assert await client.ping()


async def test_stdio_fastmcp_1_call(fastmcp1_server: FastMCP1Server):
    async with Client(transport=FastMCPTransport(fastmcp1_server)) as client:
        result = await client.call_tool(name="plus_one", arguments={"x": 1})
        assert result[0].text == "2"  # type: ignore[attr-defined]


async def test_shttp_ping(fastmcp_server: FastMCP):
    async with Client(
        transport=FastMCPTransport(fastmcp_server, transport="streamable-http")
    ) as client:
        assert await client.ping()


async def test_shttp_call(fastmcp_server: FastMCP):
    async with Client(
        transport=FastMCPTransport(fastmcp_server, transport="streamable-http")
    ) as client:
        result = await client.call_tool(name="plus_one", arguments={"x": 1})
        assert result[0].text == "2"  # type: ignore[attr-defined]


PROGRESS_MESSAGES = []


@pytest.fixture(autouse=True)
def clear_progress_messages():
    yield
    PROGRESS_MESSAGES.clear()


async def progress_handler(
    progress: float, total: float | None, message: str | None
) -> None:
    PROGRESS_MESSAGES.append(dict(progress=progress, total=total, message=message))


async def test_progress_handler_stdio(fastmcp_server: FastMCP):
    async with Client(
        transport=FastMCPTransport(fastmcp_server), progress_handler=progress_handler
    ) as client:
        await client.call_tool("progress_tool", {})

        assert PROGRESS_MESSAGES == [
            dict(progress=1, total=3, message="33.33% complete"),
            dict(progress=2, total=3, message="66.67% complete"),
            dict(progress=3, total=3, message="100.00% complete"),
        ]


async def test_progress_handler_shttp(fastmcp_server: FastMCP):
    """
    The basic in-process approach does NOT support streaming like progress
    messages or other features that use SSE.
    """
    async with Client(
        transport=FastMCPTransport(fastmcp_server, transport="streamable-http"),
        progress_handler=progress_handler,
    ) as client:
        await client.call_tool("progress_tool", {})

        # NO MESSAGES RECEIVED
        assert PROGRESS_MESSAGES == []
