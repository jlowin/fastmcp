import functools

import pytest

from fastmcp import Client, Context, FastMCP


@pytest.fixture
def fastmcp_server():
    mcp = FastMCP()

    @mcp.tool
    async def list_roots(context: Context) -> list[str]:
        roots = await context.list_roots()
        return [str(r.uri) for r in roots]

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
        # ctx.list_roots is a legacy-era server-initiated feature.
        async with Client(fastmcp_server, mode="legacy", roots=roots) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == [
                "file://x/y/z",
                "file://x/y/z",
            ]

    async def test_bound_method_roots_handler(self, fastmcp_server: FastMCP):
        class RootsProvider:
            async def get_roots(self, _context: object) -> list[str]:
                return ["file:///bound-method"]

        provider = RootsProvider()

        async with Client(
            fastmcp_server, mode="legacy", roots=provider.get_roots
        ) as client:
            result = await client.call_tool("list_roots", {})

        assert result.data == ["file:///bound-method"]

    async def test_partial_roots_handler(self, fastmcp_server: FastMCP):
        async def get_roots(prefix: str, _context: object) -> list[str]:
            return [f"file:///{prefix}"]

        handler = functools.partial(get_roots, "partial")

        async with Client(fastmcp_server, mode="legacy", roots=handler) as client:
            result = await client.call_tool("list_roots", {})

        assert result.data == ["file:///partial"]
