import pytest

from fastmcp import Client, Context, FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.utilities.tests import run_server_in_process


def make_server() -> FastMCP:
    server = FastMCP("StatelessUnsupported")

    @server.tool
    async def do_elicit(ctx: Context) -> str:
        result = await ctx.elicit("What is your name?", response_type=str)
        if result.action == "accept":
            return f"Hello, {result.data}!"
        return "No name"

    @server.tool
    async def do_sample(ctx: Context) -> str:
        content = await ctx.sample("Say hello")
        return getattr(content, "text", "")

    return server


def run_http_server(host: str, port: int) -> None:
    server = make_server()
    # Enable stateless HTTP mode
    server.run(transport="http", host=host, port=port, stateless_http=True)


@pytest.mark.asyncio
async def test_elicit_raises_in_stateless_http():
    with run_server_in_process(run_http_server) as base_url:
        async with Client(
            transport=StreamableHttpTransport(f"{base_url}/mcp/")
        ) as client:
            with pytest.raises(
                ToolError, match="Elicitation is not supported in stateless HTTP mode"
            ):
                await client.call_tool("do_elicit", {})


@pytest.mark.asyncio
async def test_sample_raises_in_stateless_http():
    with run_server_in_process(run_http_server) as base_url:
        async with Client(
            transport=StreamableHttpTransport(f"{base_url}/mcp/")
        ) as client:
            with pytest.raises(
                ToolError, match="Sampling is not supported in stateless HTTP mode"
            ):
                await client.call_tool("do_sample", {})


def test_is_stateless_http_resets_between_app_creations():
    """Ensure _current_stateless_http is reset when switching transports.

    This simulates a reload scenario where the same FastMCP instance may create
    multiple apps sequentially without a full process restart.
    """
    server = make_server()

    # First, create an HTTP app with stateless mode enabled
    server.http_app(transport="http", stateless_http=True)
    assert server.is_stateless_http is True

    # Next, create an SSE app which should always reset to stateful
    server.http_app(transport="sse")
    assert server.is_stateless_http is False

    # Finally, create an HTTP app again without stateless flag (defaults False)
    server.http_app(transport="http")
    assert server.is_stateless_http is False
