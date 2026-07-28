"""End-to-end round-trip tests for Prefab peer-tool references.

These simulate what a real host does: call the UI tool, extract the
hashed backend-tool name from structured_content, call back with
that name, and verify the backend tool actually executes. Covers
single-server, namespaced mounts, and cross-server mounts.
"""

from __future__ import annotations

import pytest

from fastmcp import FastMCP, FastMCPApp
from fastmcp.exceptions import ToolError
from fastmcp.experimental.transforms.code_mode import CodeMode
from fastmcp.server.providers.addressing import hash_tool, hashed_backend_name
from fastmcp.server.providers.proxy import ProxyClient, ProxyProvider
from fastmcp.server.transforms.search import RegexSearchTransform

prefab_ui = pytest.importorskip("prefab_ui")
from prefab_ui.actions.mcp import CallTool  # noqa: E402
from prefab_ui.components import Button, Column, Text  # noqa: E402


def _tool_refs(payload) -> list[str]:
    """Every tool name the rendered UI would call, in document order."""
    refs: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("action") == "toolCall" and isinstance(node.get("tool"), str):
                refs.append(node["tool"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return refs


class TestSingleServerRoundTrip:
    async def test_payload_carries_the_servers_own_tool_name(self):
        """The renderer is handed a name that exists in this server's
        tools/list, not the identity-addressed form."""
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
        assert _tool_refs(result.structured_content) == ["save_contact"]

    async def test_payload_records_the_identity_behind_each_reference(self):
        """The identity-addressed form survives alongside the rewritten name,
        so an outer server can re-resolve it — or fall back to it."""
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
        names = result.structured_content["_meta"]["fastmcp"]["toolNames"]
        assert names == {
            "save_contact": hashed_backend_name("contacts", "save_contact")
        }

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


class TestLateBoundToolNames:
    """The payload is re-addressed on the way out of every FastMCP server.

    Servers unwind innermost-first, so the outermost one rewrites last and its
    names — the only ones a client can invoke — are what the renderer receives.
    """

    @staticmethod
    def _app(marker: str = "x", app_name: str = "contacts") -> FastMCPApp:
        app = FastMCPApp(app_name)

        @app.tool()
        def save(name: str) -> str:
            return f"[{marker}] saved {name}"

        @app.ui()
        def form() -> Column:
            return Column(
                children=[Button(label="Save", on_click=CallTool(tool="save"))]
            )

        return app

    async def test_namespaced_server_emits_its_namespaced_name(self):
        server = FastMCP("Platform")
        server.add_provider(self._app(), namespace="crm")

        result = await server.call_tool("crm_form", {})
        assert _tool_refs(result.structured_content) == ["crm_save"]

    async def test_name_accumulates_through_nested_mounts(self):
        inner = FastMCP("Inner")
        inner.add_provider(self._app(), namespace="a")
        mid = FastMCP("Mid")
        mid.add_provider(inner, namespace="b")
        top = FastMCP("Top")
        top.add_provider(mid, namespace="c")

        result = await top.call_tool("c_b_a_form", {})
        assert _tool_refs(result.structured_content) == ["c_b_a_save"]

    async def test_gateway_emits_its_own_name_not_the_backends(self):
        backend = FastMCP("Backend")
        backend.add_provider(self._app())

        gateway = FastMCP("Gateway")
        gateway.add_provider(
            ProxyProvider(lambda: ProxyClient(backend)), namespace="up"
        )

        result = await gateway.call_tool("up_form", {})
        assert _tool_refs(result.structured_content) == ["up_save"]

    async def test_emitted_name_is_callable_on_the_same_server(self):
        """The whole point: what the renderer is told to call, it can call."""
        backend = FastMCP("Backend")
        backend.add_provider(self._app(marker="be"))

        gateway = FastMCP("Gateway")
        gateway.add_provider(
            ProxyProvider(lambda: ProxyClient(backend)), namespace="up"
        )

        result = await gateway.call_tool("up_form", {})
        (ref,) = _tool_refs(result.structured_content)
        assert ref in [t.name for t in await gateway.list_tools()]

        clicked = await gateway.call_tool(ref, {"name": "alice"})
        assert clicked.content[0].text == "[be] saved alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_each_branch_resolves_within_itself(self):
        """One app composed twice: each tenant's UI addresses its own tool."""
        first = FastMCP("TenantA")
        first.add_provider(self._app(marker="A"), namespace="inner")
        second = FastMCP("TenantB")
        second.add_provider(self._app(marker="B"), namespace="inner")

        top = FastMCP("Top")
        top.add_provider(first, namespace="a")
        top.add_provider(second, namespace="b")

        for branch, marker in (("a", "A"), ("b", "B")):
            result = await top.call_tool(f"{branch}_inner_form", {})
            (ref,) = _tool_refs(result.structured_content)
            assert ref == f"{branch}_inner_save"

            clicked = await top.call_tool(ref, {"name": "alice"})
            assert clicked.content[0].text == f"[{marker}] saved alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    @pytest.mark.parametrize(
        "transform_factory,expected_listing",
        [
            (
                lambda: RegexSearchTransform(),
                ["search_tools", "call_tool"],
            ),
            (
                lambda: CodeMode(),
                ["search", "get_schema", "execute"],
            ),
        ],
        ids=["tool-search", "code-mode"],
    )
    async def test_survives_a_collapsed_catalog(
        self, transform_factory, expected_listing
    ):
        """Tool search and code mode replace tools/list wholesale, so there is
        no better name to bind to. The reference stays identity-addressed and
        the hashed path still resolves it."""
        server = FastMCP("Platform")
        server.add_provider(self._app(marker="cat"))
        server.add_transform(transform_factory())

        assert [t.name for t in await server.list_tools()] == expected_listing

        result = await server.call_tool("form", {})
        (ref,) = _tool_refs(result.structured_content)
        assert ref == hashed_backend_name("contacts", "save")

        clicked = await server.call_tool(ref, {"name": "alice"})
        assert clicked.content[0].text == "[cat] saved alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_branch_is_tracked_not_inferred_from_names(self):
        """Namespaces whose names prefix one another must not cross-resolve.

        With namespaces `a` and `a_form`, the entry tool `a_form` belongs to
        branch `a` while `a_form_save` belongs to branch `a_form`. Anything
        matching on name similarity picks the longer shared prefix and routes
        into the wrong branch.
        """
        top = FastMCP("Top")
        top.add_provider(self._app(marker="A"), namespace="a")
        top.add_provider(self._app(marker="AFORM"), namespace="a_form")

        result = await top.call_tool("a_form", {})
        (ref,) = _tool_refs(result.structured_content)
        assert ref == "a_save"

        clicked = await top.call_tool(ref, {"name": "alice"})
        assert clicked.content[0].text == "[A] saved alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

        other = await top.call_tool("a_form_form", {})
        (other_ref,) = _tool_refs(other.structured_content)
        assert other_ref == "a_form_save"

        other_clicked = await top.call_tool(other_ref, {"name": "alice"})
        assert other_clicked.content[0].text == "[AFORM] saved alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_duplicate_apps_nested_in_one_subtree(self):
        """Both copies can live inside a single provider, so the copy cannot
        be identified by which of this server's providers served the call."""
        inner = FastMCP("Inner")
        inner.add_provider(self._app(marker="A"), namespace="a")
        inner.add_provider(self._app(marker="B"), namespace="b")

        outer = FastMCP("Outer")
        outer.add_provider(inner, namespace="outer")

        listing = [t.name for t in await outer.list_tools()]
        for branch, marker in (("a", "A"), ("b", "B")):
            result = await outer.call_tool(f"outer_{branch}_form", {})
            (ref,) = _tool_refs(result.structured_content)
            assert ref == f"outer_{branch}_save"
            assert ref in listing

            clicked = await outer.call_tool(ref, {"name": "alice"})
            assert clicked.content[0].text == f"[{marker}] saved alice"  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]

    async def test_unresolvable_identity_is_restored(self):
        """An inner server binds to a name that means nothing further out, so
        a reference this server cannot resolve is restored to its identity
        rather than left — a stranded name has no route back, an identity does.
        """
        app = FastMCPApp("contacts")

        @app.ui()
        def form() -> Column:
            return Column(
                children=[Button(label="Go", on_click=CallTool(tool="not_registered"))]
            )

        server = FastMCP("Platform")
        server.add_provider(app)

        result = await server.call_tool("form", {})
        (ref,) = _tool_refs(result.structured_content)
        assert ref == hashed_backend_name("contacts", "not_registered")


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
