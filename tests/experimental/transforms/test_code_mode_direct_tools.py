"""Direct tools retain native MCP schemas alongside the CodeMode surface."""

from typing import Any, Literal

import pytest

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.experimental.transforms.code_mode import (
    CodeMode,
    GetSchemas,
    GetTags,
    GetToolCatalog,
    ListTools,
    Search,
)
from fastmcp.server.context import Context
from fastmcp.server.transforms import Namespace
from fastmcp.tools import Tool
from fastmcp.utilities.versions import VersionSpec


async def test_direct_tool_keeps_schema_metadata_and_native_call() -> None:
    mcp = FastMCP("Direct tools")

    @mcp.tool(tags={"instructions"}, meta={"purpose": "onboarding"})
    def load_skill(skill: Literal["research", "review"]) -> str:
        """Load instructions for a skill."""
        return f"Instructions for {skill}"

    @mcp.tool
    def add(x: int, y: int) -> int:
        return x + y

    original = await mcp.get_tool("load_skill")
    assert original is not None
    mcp.add_transform(CodeMode(direct_tool_names={"load_skill"}))

    async with Client(mcp) as client:
        listed = {tool.name: tool for tool in await client.list_tools()}
        assert set(listed) == {"search", "get_schema", "execute", "load_skill"}
        assert listed["load_skill"].input_schema == original.parameters
        assert listed["load_skill"].meta == original.get_meta()
        direct = await client.call_tool("load_skill", {"skill": "research"})
        assert direct.data == "Instructions for research"
        executed = await client.call_tool(
            "execute", {"code": "return await call_tool('add', {'x': 2, 'y': 3})"}
        )
        assert executed.data == {"result": 5}
        with pytest.raises(ToolError, match="Unknown tool: load_skill"):
            await client.call_tool(
                "execute",
                {"code": "return await call_tool('load_skill', {'skill': 'review'})"},
            )


@pytest.mark.parametrize("discovery", [Search, GetSchemas, GetTags, ListTools])
async def test_direct_tools_excluded_from_every_discovery(
    discovery: type[Search | GetSchemas | GetTags | ListTools],
) -> None:
    mcp = FastMCP("Direct discovery")

    @mcp.tool(tags={"direct_only"})
    def load_skill() -> str:
        """Load a skill."""
        return "instructions"

    @mcp.tool(tags={"backend"})
    def calculate() -> int:
        """Calculate something."""
        return 42

    mcp.add_transform(
        CodeMode(
            direct_tool_names={"load_skill"},
            discovery_tools=[discovery(name="discover")],
        )
    )
    arguments: dict[str, Any] = (
        {"query": "skill calculate"} if discovery is Search else {}
    )
    if discovery is GetSchemas:
        arguments = {"tools": ["load_skill", "calculate"]}
    async with Client(mcp) as client:
        result = await client.call_tool("discover", arguments)
        text = str(result.data)
        assert "direct_only" not in text
        assert ("backend" if discovery is GetTags else "calculate") in text
        # GetSchemas explicitly reports the requested missing name.
        if discovery is GetSchemas:
            assert "Tools not found: load_skill" in text
            assert "Load a skill" not in text
        else:
            assert "load_skill" not in text


async def test_custom_discovery_receives_filtered_catalog() -> None:
    def catalog_names(get_catalog: GetToolCatalog) -> Tool:
        async def names(ctx: Context) -> list[str]:
            return [tool.name for tool in await get_catalog(ctx)]

        return Tool.from_function(names)

    mcp = FastMCP("Custom discovery")

    @mcp.tool
    def direct() -> None:
        pass

    @mcp.tool
    def backend() -> None:
        pass

    mcp.add_transform(
        CodeMode(direct_tool_names={"direct"}, discovery_tools=[catalog_names])
    )
    async with Client(mcp) as client:
        assert (await client.call_tool("names")).data == ["backend"]


@pytest.mark.parametrize("disable_latest", [False, True])
async def test_direct_versions_use_native_selection_and_fallback(
    disable_latest: bool,
) -> None:
    mcp = FastMCP("Direct versions")

    @mcp.tool(name="load_skill", version="1", tags={"old"})
    def old_skill(old: str) -> str:
        return f"old {old}"

    @mcp.tool(name="load_skill", version="2", tags={"new"})
    def new_skill(new: int) -> str:
        return f"new {new}"

    if disable_latest:
        mcp.disable(names={"load_skill"}, version=VersionSpec(eq="2"))
    mcp.add_transform(CodeMode(direct_tool_names={"load_skill"}))

    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        parameters = tools["load_skill"].input_schema["properties"]
        argument = {"old": "skill"} if disable_latest else {"new": 2}
        assert set(parameters) == set(argument)
        assert (await client.call_tool("load_skill", argument)).data == (
            "old skill" if disable_latest else "new 2"
        )
        catalog = await client.call_tool("get_schema", {"tools": ["load_skill"]})
        assert "Tools not found: load_skill" in str(catalog.data)


@pytest.mark.parametrize("restricted_by", ["disabled", "auth"])
async def test_direct_tools_respect_visibility_and_auth(restricted_by: str) -> None:
    mcp = FastMCP("Restricted direct tools")

    @mcp.tool(auth=(lambda _ctx: False) if restricted_by == "auth" else None)
    def secret() -> str:
        return "secret value"

    if restricted_by == "disabled":
        mcp.disable(names={"secret"})
    mcp.add_transform(CodeMode(direct_tool_names={"secret"}))

    async with Client(mcp) as client:
        assert "secret" not in {tool.name for tool in await client.list_tools()}
        with pytest.raises(ToolError):
            await client.call_tool("secret")
        with pytest.raises(ToolError, match="Unknown tool: secret"):
            await client.call_tool(
                "execute", {"code": "return await call_tool('secret', {})"}
            )


@pytest.mark.parametrize("namespace_first", [False, True])
async def test_direct_names_follow_transform_position(namespace_first: bool) -> None:
    mcp = FastMCP("Namespaced direct tools")

    @mcp.tool
    def load_skill() -> str:
        return "instructions"

    @mcp.tool
    def calculate() -> int:
        return 42

    code_mode = CodeMode(
        direct_tool_names={"api_load_skill" if namespace_first else "load_skill"},
        discovery_tools=[ListTools()],
    )
    transforms = [Namespace("api"), code_mode]
    if not namespace_first:
        transforms.reverse()
    for transform in transforms:
        mcp.add_transform(transform)

    synthetic_prefix = "" if namespace_first else "api_"
    async with Client(mcp) as client:
        listed = {tool.name for tool in await client.list_tools()}
        assert listed == {
            "api_load_skill",
            f"{synthetic_prefix}list_tools",
            f"{synthetic_prefix}execute",
        }
        assert (await client.call_tool("api_load_skill")).data == "instructions"
        catalog = await client.call_tool(f"{synthetic_prefix}list_tools")
        assert "api_calculate" in str(catalog.data)
        assert "load_skill" not in str(catalog.data)
        with pytest.raises(ToolError, match="Unknown tool: api_load_skill"):
            await client.call_tool(
                f"{synthetic_prefix}execute",
                {"code": "return await call_tool('api_load_skill', {})"},
            )


@pytest.mark.parametrize("name", ["search", "get_schema", "execute"])
async def test_direct_names_cannot_shadow_default_synthetic_tools(name: str) -> None:
    mode = CodeMode(direct_tool_names={name})
    with pytest.raises(ValueError, match=f"Direct tool names collide.*{name}"):
        await mode.transform_tools([])


@pytest.mark.parametrize("name", ["find", "run"])
async def test_direct_names_cannot_shadow_custom_synthetic_tools(name: str) -> None:
    mcp = FastMCP(
        "Collision",
        transforms=[
            CodeMode(
                direct_tool_names={name},
                discovery_tools=[Search(name="find")],
                execute_tool_name="run",
            )
        ],
    )
    with pytest.raises(ValueError, match=f"Direct tool names collide.*{name}"):
        await mcp.get_tool(name)


@pytest.mark.parametrize("direct_names", [None, set(), {"absent"}])
async def test_default_and_unknown_direct_names_keep_code_mode_behavior(
    direct_names: set[str] | None,
) -> None:
    mcp = FastMCP("Default behavior")

    @mcp.tool
    def load_skill() -> str:
        return "instructions"

    mcp.add_transform(CodeMode(direct_tool_names=direct_names))
    async with Client(mcp) as client:
        assert {tool.name for tool in await client.list_tools()} == {
            "search",
            "get_schema",
            "execute",
        }
        result = await client.call_tool(
            "execute", {"code": "return await call_tool('load_skill', {})"}
        )
        assert result.data == {"result": "instructions"}


@pytest.mark.parametrize("transform_on_child", [False, True])
async def test_direct_tools_on_mounted_server(transform_on_child: bool) -> None:
    child = FastMCP("Child")

    @child.tool
    def load_skill() -> str:
        return "instructions"

    @child.tool
    def calculate() -> int:
        return 42

    parent = FastMCP("Parent")
    mode = CodeMode(
        direct_tool_names={"load_skill" if transform_on_child else "api_load_skill"},
        discovery_tools=[ListTools()],
    )
    if transform_on_child:
        child.add_transform(mode)
    parent.mount(child, namespace="api")
    if not transform_on_child:
        parent.add_transform(mode)

    prefix = "api_" if transform_on_child else ""
    backend_name = "calculate" if transform_on_child else "api_calculate"
    async with Client(parent) as client:
        assert {tool.name for tool in await client.list_tools()} == {
            "api_load_skill",
            f"{prefix}list_tools",
            f"{prefix}execute",
        }
        assert (await client.call_tool("api_load_skill")).data == "instructions"
        catalog = await client.call_tool(f"{prefix}list_tools")
        assert backend_name in str(catalog.data)
        assert "load_skill" not in str(catalog.data)
        executed = await client.call_tool(
            f"{prefix}execute",
            {"code": f"return await call_tool('{backend_name}', {{}})"},
        )
        assert executed.data == {"result": 42}
