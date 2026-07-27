"""End-to-end round-trip tests for Prefab peer-tool references.

These simulate what a real host does: call the UI tool, extract the
hashed backend-tool name from structured_content, call back with
that name, and verify the backend tool actually executes. Covers
single-server, namespaced mounts, and cross-server mounts.
"""

from __future__ import annotations

import json

import pytest

from fastmcp import FastMCP, FastMCPApp
from fastmcp.exceptions import ToolError
from fastmcp.server.providers.addressing import hash_tool, hashed_backend_name
from fastmcp.server.providers.proxy import ProxyClient, ProxyProvider

prefab_ui = pytest.importorskip("prefab_ui")
from prefab_ui.actions.mcp import CallTool  # noqa: E402
from prefab_ui.components import Button, Column, Text  # noqa: E402


class TestSingleServerRoundTrip:
    async def test_ui_tool_serializes_hashed_peer_reference(self):
        """The resolver converts a CallTool string reference to a hashed
        name that appears in the tool result's structured_content."""
        app = FastMCPApp("contacts")

        @app.tool()
        def save_contact(name: str) -> str:
            return f"saved {name}"

        @app.ui()
        def contact_form() -> Column:
            return Column(
                children=[Button(label="Save", on_click=CallTool(tool="save_contact"))]
            )

        server = FastMCP("Platform")
        server.add_provider(app)

        result = await server.call_tool("contact_form", {})
        assert result.structured_content is not None

        # The hashed name should appear somewhere in the serialized output.
        sc_json = json.dumps(result.structured_content)
        expected_hash = hashed_backend_name("contacts", "save_contact")
        assert expected_hash in sc_json, (
            f"Expected {expected_hash!r} in structured_content but got: {sc_json[:200]}"
        )

    async def test_hashed_name_from_result_is_callable(self):
        """The hashed name that appears in structured_content actually
        resolves when called back — the full round-trip works."""
        app = FastMCPApp("contacts")

        @app.tool()
        def save_contact(name: str) -> str:
            return f"saved {name}"

        @app.ui()
        def contact_form() -> Column:
            return Column(
                children=[Button(label="Save", on_click=CallTool(tool="save_contact"))]
            )

        server = FastMCP("Platform")
        server.add_provider(app)

        # Step 1: call UI tool, get structured_content with hashed ref
        await server.call_tool("contact_form", {})

        # Step 2: call the backend tool by its hashed name
        hashed_name = hashed_backend_name("contacts", "save_contact")
        backend_result = await server.call_tool(hashed_name, {"name": "Alice"})
        assert backend_result.content[0].text == "saved Alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]


class TestNamespacedMountRoundTrip:
    async def test_namespaced_app_backend_tool_round_trip(self):
        """A FastMCPApp mounted with a namespace: the UI tool is called
        by its namespaced display name, the backend tool is called by
        its hashed name — both work."""
        app = FastMCPApp("crm")

        @app.tool()
        def save(name: str) -> str:
            return f"saved {name}"

        @app.ui()
        def form() -> Text:
            return Text(content="Enter details")

        server = FastMCP("Platform")
        server.add_provider(app, namespace="crm")

        # UI tool visible under namespace
        result = await server.call_tool("crm_form", {})
        assert result.structured_content is not None

        # Backend tool reachable via hash
        hashed_name = hashed_backend_name("crm", "save")
        backend_result = await server.call_tool(hashed_name, {"name": "Bob"})
        assert backend_result.content[0].text == "saved Bob"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]


class TestMountedServerRoundTrip:
    async def test_backend_tool_reachable_through_mounted_server(self):
        """A FastMCPApp inside a mounted FastMCP server: the outer
        server's dispatcher walks through FastMCPProvider to find
        the backend tool by hash."""
        app = FastMCPApp("contacts")

        @app.tool()
        def save(name: str) -> str:
            return f"saved {name}"

        @app.ui()
        def form() -> Text:
            return Text(content="Form")

        inner = FastMCP("Inner")
        inner.add_provider(app)

        outer = FastMCP("Outer")
        outer.mount(inner, namespace="inner")

        # Backend tool callable through the mount via hash dispatch
        hashed_name = hashed_backend_name("contacts", "save")
        result = await outer.call_tool(hashed_name, {"name": "Carol"})
        assert result.content[0].text == "saved Carol"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]


class TestProxiedServerRoundTrip:
    """A gateway proxying an app-bearing backend.

    A proxy knows only what crossed the wire, so this is the topology that
    breaks if app-only tools are filtered out of tools/list or if the
    identity hash is stripped from meta.
    """

    @staticmethod
    def _backend() -> FastMCP:
        app = FastMCPApp("contacts")

        @app.tool()
        def save(name: str) -> str:
            return f"saved {name}"

        @app.ui()
        def form() -> Text:
            return Text(content="Form")

        backend = FastMCP("Backend")
        backend.add_provider(app)
        return backend

    async def test_app_only_tool_is_forwarded_through_a_proxy(self):
        backend = self._backend()
        gateway = FastMCP("Gateway")
        gateway.add_provider(ProxyProvider(lambda: ProxyClient(backend)))

        names = [t.name for t in await gateway.list_tools()]
        assert "save" in names

    async def test_identity_hash_survives_the_proxy(self):
        backend = self._backend()
        gateway = FastMCP("Gateway")
        gateway.add_provider(ProxyProvider(lambda: ProxyClient(backend)))

        tool = next(t for t in await gateway.list_tools() if t.name == "save")
        assert tool.meta is not None
        assert tool.meta["fastmcp"]["tool_hash"] == hash_tool("contacts", "save")

    async def test_backend_tool_callable_by_hash_through_a_proxy(self):
        backend = self._backend()
        gateway = FastMCP("Gateway")
        gateway.add_provider(ProxyProvider(lambda: ProxyClient(backend)))

        hashed_name = hashed_backend_name("contacts", "save")
        result = await gateway.call_tool(hashed_name, {"name": "Dana"})
        assert result.content[0].text == "saved Dana"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_backend_tool_callable_through_a_namespaced_proxy(self):
        backend = self._backend()
        gateway = FastMCP("Gateway")
        gateway.add_provider(
            ProxyProvider(lambda: ProxyClient(backend)), namespace="up"
        )

        names = [t.name for t in await gateway.list_tools()]
        assert "up_save" in names

        hashed_name = hashed_backend_name("contacts", "save")
        result = await gateway.call_tool(hashed_name, {"name": "Erin"})
        assert result.content[0].text == "saved Erin"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_backend_tool_callable_through_chained_proxies(self):
        backend = self._backend()
        middle = FastMCP("Middle")
        middle.add_provider(ProxyProvider(lambda: ProxyClient(backend)))
        top = FastMCP("Top")
        top.add_provider(ProxyProvider(lambda: ProxyClient(middle)))

        hashed_name = hashed_backend_name("contacts", "save")
        result = await top.call_tool(hashed_name, {"name": "Frank"})
        assert result.content[0].text == "saved Frank"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]


class TestDynamicToolAdd:
    async def test_tool_added_after_first_call_is_reachable(self):
        """Tools added to an already-mounted app after the first call
        are still reachable via their hashed name — get_tool_by_hash
        does a live walk, not a cached lookup."""
        app = FastMCPApp("contacts")

        server = FastMCP("Platform")
        server.add_provider(app)

        # First call — nothing to call yet, just prime any caches.
        tools = await server.list_tools()
        assert len(tools) == 0

        # Now add a backend tool dynamically.
        @app.tool()
        def save(name: str) -> str:
            return f"saved {name}"

        # The dynamically-added tool should be reachable.
        hashed_name = hashed_backend_name("contacts", "save")
        result = await server.call_tool(hashed_name, {"name": "Dan"})
        assert result.content[0].text == "saved Dan"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]


class TestCollision:
    async def test_distinct_hashes_resolve_independently(self):
        """Two apps sharing a name but with different tool names hash
        differently, so each tool resolves to itself."""
        app_a = FastMCPApp("shared")
        app_b = FastMCPApp("shared")

        @app_a.tool()
        def save(name: str) -> str:
            return f"from A: {name}"

        @app_b.tool()
        def save_b(name: str) -> str:
            return f"from B: {name}"

        server = FastMCP("Platform")
        server.add_provider(app_a)
        server.add_provider(app_b)

        result = await server.call_tool(
            hashed_backend_name("shared", "save"), {"name": "Eve"}
        )
        assert result.content[0].text == "from A: Eve"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

        result_b = await server.call_tool(
            hashed_backend_name("shared", "save_b"), {"name": "Eve"}
        )
        assert result_b.content[0].text == "from B: Eve"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_ambiguous_identity_raises_rather_than_guessing(self):
        """The same app composed into two branches yields two tools with one
        identity. Routing to either would silently execute the wrong branch's
        tool, so the call is refused."""
        server = FastMCP("Platform")
        for marker, namespace in (("A", "a"), ("B", "b")):
            app = FastMCPApp("contacts")

            @app.tool()
            def save(name: str, _marker: str = marker) -> str:
                return f"from {_marker}: {name}"

            server.add_provider(app, namespace=namespace)

        with pytest.raises(ToolError, match="Ambiguous app tool"):
            await server.call_tool(
                hashed_backend_name("contacts", "save"), {"name": "Eve"}
            )

    async def test_distinct_app_names_route_independently_through_a_gateway(self):
        """The multi-tenant gateway shape: distinct app names stay unambiguous
        no matter how many backends sit behind one proxy."""

        def backend(marker: str, app_name: str) -> FastMCP:
            app = FastMCPApp(app_name)

            @app.tool()
            def save(name: str) -> str:
                return f"from {marker}: {name}"

            server = FastMCP(f"Backend-{marker}")
            server.add_provider(app)
            return server

        first = backend("A", "crm")
        second = backend("B", "billing")

        gateway = FastMCP("Gateway")
        gateway.add_provider(ProxyProvider(lambda: ProxyClient(first)), namespace="a")
        gateway.add_provider(ProxyProvider(lambda: ProxyClient(second)), namespace="b")

        result_a = await gateway.call_tool(
            hashed_backend_name("crm", "save"), {"name": "Eve"}
        )
        assert result_a.content[0].text == "from A: Eve"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

        result_b = await gateway.call_tool(
            hashed_backend_name("billing", "save"), {"name": "Eve"}
        )
        assert result_b.content[0].text == "from B: Eve"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]
