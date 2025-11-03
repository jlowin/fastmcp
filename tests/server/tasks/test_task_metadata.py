"""
Tests for SEP-1686 related-task metadata in protocol responses.

Per the spec, all task-related responses MUST include
modelcontextprotocol.io/related-task in _meta.
"""

import pytest

from fastmcp import FastMCP
from fastmcp.client import Client


@pytest.fixture
async def metadata_server():
    """Create a server for testing metadata."""
    mcp = FastMCP("metadata-test")

    @mcp.tool(task=True)
    async def test_tool(value: int) -> int:
        return value * 2

    return mcp


async def test_tasks_get_includes_related_task_metadata(metadata_server: FastMCP):
    """tasks/get response includes modelcontextprotocol.io/related-task in _meta."""
    async with Client(metadata_server) as client:
        # Submit a task
        task = await client.call_tool_as_task("test_tool", {"value": 5})
        task_id = task.task_id

        # Get status via direct protocol call
        # For FastMCPTransport, call the handler directly
        from fastmcp.client.transports import FastMCPTransport

        if isinstance(client.transport, FastMCPTransport):
            server = client.transport.server
            response = await server._tasks_get_mcp({"taskId": task_id})

            # Verify related-task metadata is present
            assert "_meta" in response
            assert "modelcontextprotocol.io/related-task" in response["_meta"]
            assert (
                response["_meta"]["modelcontextprotocol.io/related-task"]["taskId"]
                == task_id
            )


async def test_tasks_result_includes_related_task_metadata(metadata_server: FastMCP):
    """tasks/result response includes modelcontextprotocol.io/related-task in _meta."""
    async with Client(metadata_server) as client:
        # Submit and complete a task
        task = await client.call_tool_as_task("test_tool", {"value": 7})
        await task.wait(timeout=2.0)
        task_id = task.task_id

        # Get result via direct protocol call
        from fastmcp.client.transports import FastMCPTransport

        if isinstance(client.transport, FastMCPTransport):
            server = client.transport.server
            result = await server._tasks_result_mcp({"taskId": task_id})

            # Verify related-task metadata is present
            # MCP types use 'meta' field (Python) which serializes to '_meta' (JSON)
            if hasattr(result, "meta"):
                meta = result.meta
            elif isinstance(result, dict) and "_meta" in result:
                meta = result["_meta"]
            else:
                raise AssertionError(f"Result has no metadata: {result}")

            assert meta is not None
            assert "modelcontextprotocol.io/related-task" in meta
            assert meta["modelcontextprotocol.io/related-task"]["taskId"] == task_id


async def test_tasks_list_includes_related_task_metadata(metadata_server: FastMCP):
    """tasks/list response includes modelcontextprotocol.io/related-task in _meta."""
    async with Client(metadata_server) as client:
        # List tasks via direct protocol call
        from fastmcp.client.transports import FastMCPTransport

        if isinstance(client.transport, FastMCPTransport):
            server = client.transport.server
            response = await server._tasks_list_mcp({})

            # Verify related-task metadata is present
            # Note: tasks/list doesn't have a specific taskId, but should still have _meta
            # The spec says "all responses" so let's verify structure
            assert "_meta" in response


async def test_tasks_delete_includes_related_task_metadata(metadata_server: FastMCP):
    """tasks/delete response includes modelcontextprotocol.io/related-task in _meta."""
    async with Client(metadata_server) as client:
        # Submit a task
        task = await client.call_tool_as_task("test_tool", {"value": 9})
        task_id = task.task_id

        # Wait for completion
        await task.wait(timeout=2.0)

        # Delete via direct protocol call
        from fastmcp.client.transports import FastMCPTransport

        if isinstance(client.transport, FastMCPTransport):
            server = client.transport.server
            response = await server._tasks_delete_mcp({"taskId": task_id})

            # Verify related-task metadata is present
            assert "_meta" in response
            assert "modelcontextprotocol.io/related-task" in response["_meta"]
            assert (
                response["_meta"]["modelcontextprotocol.io/related-task"]["taskId"]
                == task_id
            )
