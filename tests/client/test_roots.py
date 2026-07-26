import functools

import mcp_types
import pytest

from fastmcp import Client, Context, FastMCP
from fastmcp.client.roots import create_roots_callback, convert_roots_list


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


class TestRootsHandlerCallable:
    """Regression tests for issue #4638: callable roots handlers.

    Bound methods, functools.partial, and other callables should be accepted
    as roots handlers, not just plain functions.
    """

    async def test_bound_method_accepted(self, fastmcp_server: FastMCP):
        class RootsProvider:
            async def get_roots(self, _context):
                return ["file:///bound-method"]

        handler = RootsProvider().get_roots
        async with Client(fastmcp_server, mode="legacy", roots=handler) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == ["file:///bound-method"]

    async def test_partial_accepted(self, fastmcp_server: FastMCP):
        async def get_roots(prefix, _context):
            return [f"file:///{prefix}"]

        handler = functools.partial(get_roots, "partial-root")
        async with Client(fastmcp_server, mode="legacy", roots=handler) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == ["file:///partial-root"]

    async def test_lambda_accepted(self, fastmcp_server: FastMCP):
        handler = lambda _context: ["file:///lambda-root"]
        async with Client(fastmcp_server, mode="legacy", roots=handler) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == ["file:///lambda-root"]

    async def test_callable_object_accepted(self, fastmcp_server: FastMCP):
        class CallableRoots:
            async def __call__(self, _context):
                return ["file:///callable-object"]

        async with Client(fastmcp_server, mode="legacy", roots=CallableRoots()) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == ["file:///callable-object"]

    async def test_non_callable_rejected(self, fastmcp_server: FastMCP):
        with pytest.raises(ValueError, match="Invalid roots handler"):
            Client(fastmcp_server, roots="not-a-handler")

    async def test_sync_function_accepted(self, fastmcp_server: FastMCP):
        def sync_handler(_context):
            return ["file:///sync-root"]

        async with Client(fastmcp_server, mode="legacy", roots=sync_handler) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == ["file:///sync-root"]

    def test_create_roots_callback_rejects_non_callable(self):
        with pytest.raises(ValueError, match="Invalid roots handler"):
            create_roots_callback(42)


class TestRootsErrorHandling:
    """Test error paths in roots callback and conversion."""

    async def test_handler_exception_returns_error(self, fastmcp_server: FastMCP):
        async def failing_handler(_context):
            raise RuntimeError("roots handler failed")

        from fastmcp.exceptions import ToolError

        async with Client(fastmcp_server, mode="legacy", roots=failing_handler) as client:
            with pytest.raises(ToolError, match="roots handler failed"):
                await client.call_tool("list_roots", {})

    async def test_roots_list_with_root_objects(self, fastmcp_server: FastMCP):
        roots = [mcp_types.Root(uri="file:///from-root-obj", name="my-root")]
        async with Client(fastmcp_server, mode="legacy", roots=roots) as client:
            result = await client.call_tool("list_roots", {})
            assert result.data == ["file:///from-root-obj"]

    def test_convert_roots_list_rejects_invalid_element(self):
        with pytest.raises(ValueError, match="Invalid root"):
            convert_roots_list([42])  # type: ignore[list-item]
