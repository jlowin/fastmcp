import json
from enum import Enum

from fastmcp import Client, FastMCP
from fastmcp.server.middleware.schema_dereference import (
    SchemaDereferenceMiddleware,
)


class ColorEnum(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class TestSchemaDereferenceMiddleware:
    async def test_dereference_enum_in_tool_parameters(self):
        mcp = FastMCP("SchemaDereferenceTest")
        mcp.add_middleware(SchemaDereferenceMiddleware())

        @mcp.tool
        def choose_color(color: ColorEnum) -> str:
            return color.value

        async with Client(mcp) as client:
            tools = await client.list_tools()

        tool = next(t for t in tools if t.name == "choose_color")
        schema = tool.inputSchema

        # Ensure $ref was inlined and $defs removed for simple enum case
        assert "$ref" not in json.dumps(schema)
        assert "$defs" not in schema

        assert "properties" in schema and "color" in schema["properties"]
        color_schema = schema["properties"]["color"]
        assert color_schema.get("enum") == ["red", "green", "blue"]
        assert color_schema.get("type") == "string"

    async def test_dereference_enum_in_resource_template_parameters(self):
        mcp = FastMCP("SchemaDereferenceTemplateTest")
        mcp.add_middleware(SchemaDereferenceMiddleware())

        @mcp.resource("color://{color}")
        def color_resource(color: ColorEnum) -> str:
            return color.value

        # Use internal list to inspect template parameters after middleware
        templates = await mcp._list_resource_templates()
        assert len(templates) == 1
        params = templates[0].parameters

        # Ensure $ref was inlined and $defs removed for simple enum case
        assert "$ref" not in json.dumps(params)
        assert "$defs" not in params

        assert "properties" in params and "color" in params["properties"]
        color_schema = params["properties"]["color"]
        assert color_schema.get("enum") == ["red", "green", "blue"]
        assert color_schema.get("type") == "string"
