"""Integration tests for the FastMCP 3 and FastAPI bridge."""

import base64

import pytest
from fastapi import FastAPI

from fastmcp import Client
from server import build_server


@pytest.mark.asyncio
async def test_builtin_tool_returns_image_and_structured_result():
    server = build_server(discover_components=False)

    async with Client(server) as client:
        result = await client.call_tool("add", {"a": 5, "b": 7})

    assert result.structured_content == {"sum": 12}
    assert result.content[0].type == "image"
    assert result.content[0].mime_type == "image/png"
    assert base64.b64decode(result.content[0].data).startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_fastapi_routes_are_tools_and_sensitive_routes_are_excluded():
    api = FastAPI()

    @api.get("/widgets/{widget_id}", operation_id="get_widget")
    async def get_widget(widget_id: int):
        return {"id": widget_id}

    @api.post("/widgets", operation_id="create_widget")
    async def create_widget(name: str):
        return {"name": name}

    @api.delete("/widgets/{widget_id}", operation_id="delete_widget")
    async def delete_widget(widget_id: int):
        return {"deleted": widget_id}

    @api.get("/admin/stats", operation_id="admin_stats")
    async def admin_stats():
        return {"secret": True}

    server = build_server(api, discover_components=False)
    async with Client(server) as client:
        names = {tool.name for tool in await client.list_tools()}
        result = await client.call_tool("get_widget", {"widget_id": 42})

    assert {"get_widget", "create_widget", "add"} <= names
    assert "delete_widget" not in names
    assert "admin_stats" not in names
    assert result.data == {"id": 42}


def test_building_server_does_not_remove_fastapi_routes():
    api = FastAPI()

    @api.delete("/items/{item_id}")
    async def delete_item(item_id: int):
        return {"deleted": item_id}

    route_count = len(api.routes)
    build_server(api, discover_components=False)

    assert len(api.routes) == route_count


@pytest.mark.asyncio
async def test_local_components_are_discovered():
    server = build_server()

    async with Client(server) as client:
        tool_names = {tool.name for tool in await client.list_tools()}
        prompt_names = {prompt.name for prompt in await client.list_prompts()}
        resource_uris = {
            str(resource.uri) for resource in await client.list_resources()
        }

    assert {"create_note", "create_task", "create_category", "add"} <= tool_names
    assert "note-assistant" in prompt_names
    assert "config://notes-app" in resource_uris
