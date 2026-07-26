import pytest
from mcp_types import Root

from fastmcp import Client, Context, FastMCP


@pytest.fixture
def fastmcp_server():
    """A server that issues a handshake-era `roots/list` request.

    `Context` has no `list_roots()` — server-initiated requests are not part of
    FastMCP's server API. This server reaches the SDK session directly to stand
    in for a legacy upstream, so the client's `roots=` handling stays covered.
    """
    mcp = FastMCP()

    @mcp.tool
    async def list_roots(context: Context) -> list[str]:
        result = await context.session.list_roots()
        return [str(r.uri) for r in result.roots]

    return mcp


class TestClientRoots:
    @pytest.mark.parametrize("roots", [["x"], ["x", "y"]])
    async def test_invalid_roots(self, fastmcp_server: FastMCP, roots: list[str]):
        """
        Roots must be URIs
        """
        with pytest.raises(ValueError, match="Input should be a valid URL"):
            async with Client(fastmcp_server, roots=roots):
                pass

    @pytest.mark.parametrize("roots", [["https://x.com"]])
    async def test_invalid_urls(self, fastmcp_server: FastMCP, roots: list[str]):
        """
        At this time, root URIs must start with file://
        """
        with pytest.raises(ValueError, match="URL scheme should be 'file'"):
            async with Client(fastmcp_server, roots=roots):
                pass

    @pytest.mark.parametrize("roots", [["file://x/y/z", "file://x/y/z"]])
    async def test_valid_roots(self, fastmcp_server: FastMCP, roots: list[str]):
        # `roots/list` is a server-initiated request, so it only exists on the
        # handshake era; SEP-2577 removed it from the modern protocol.
        async with Client(fastmcp_server, mode="legacy", roots=roots) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == [
                "file://x/y/z",
                "file://x/y/z",
            ]

    async def test_roots_handler_answers_a_legacy_server(self, fastmcp_server: FastMCP):
        """A callable `roots=` handler still answers a legacy server's request."""
        calls: list[object] = []

        async def roots_handler(ctx) -> list[Root]:
            calls.append(ctx)
            return [Root(uri="file://from/handler")]  # ty: ignore[invalid-argument-type]

        async with Client(
            fastmcp_server, mode="legacy", roots=roots_handler
        ) as client:
            result = await client.call_tool("list_roots", {})

        assert len(calls) == 1
        assert result.data == ["file://from/handler"]
