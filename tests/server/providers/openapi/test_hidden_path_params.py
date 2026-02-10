"""Tests for hidden path parameters in OpenAPI tool descriptions."""

import httpx
import pytest

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.server.transforms import ToolTransform
from fastmcp.tools.tool_transform import ArgTransformConfig, ToolTransformConfig


@pytest.mark.asyncio
async def test_hidden_path_parameter_not_in_description():
    """Test that hidden path parameters are not included in tool descriptions.

    This test replicates the bug described in issue #3130 where path parameters
    that are hidden via ToolTransform still appear in the tool description.
    """
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "0.1.0"},
        "paths": {
            "/hello/{not_for_agent}": {
                "get": {
                    "operationId": "hello",
                    "summary": "Say hello",
                    "parameters": [
                        {
                            "name": "not_for_agent",
                            "in": "path",
                            "required": True,
                            "description": "Secret setting",
                            "schema": {
                                "type": "string",
                                "title": "Not For Agent"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Success response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "message": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    async with httpx.AsyncClient(base_url="http://localhost:8000") as http_client:
        mcp = FastMCP.from_openapi(
            openapi_spec=openapi_spec,
            client=http_client,
        )

        # Hide not_for_agent parameter and set default
        mcp.add_transform(
            ToolTransform({
                "hello": ToolTransformConfig(
                    arguments={
                        "not_for_agent": ArgTransformConfig(
                            hide=True,
                            default="secret",
                        )
                    }
                )
            })
        )

        async with Client(mcp) as mcp_client:
            tools = await mcp_client.list_tools()
            assert len(tools) == 1

            hello_tool = tools[0]
            assert hello_tool.name == "hello"

            # The parameter should not be in the schema
            assert "not_for_agent" not in hello_tool.inputSchema.get("properties", {})

            # The BUG: parameter description should not appear in the tool description
            assert "Secret setting" not in hello_tool.description
            assert "not_for_agent" not in hello_tool.description

            # The description should only contain the summary
            assert "Say hello" in hello_tool.description


@pytest.mark.asyncio
async def test_visible_path_parameter_in_schema():
    """Test that visible path parameters are included in the inputSchema.

    Path parameters are not included in the description since they're already
    visible in the inputSchema with their descriptions.
    """
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "0.1.0"},
        "paths": {
            "/users/{user_id}": {
                "get": {
                    "operationId": "get_user",
                    "summary": "Get user by ID",
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "description": "The user's unique identifier",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Success response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "name": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    async with httpx.AsyncClient(base_url="http://localhost:8000") as http_client:
        mcp = FastMCP.from_openapi(
            openapi_spec=openapi_spec,
            client=http_client,
        )

        async with Client(mcp) as mcp_client:
            tools = await mcp_client.list_tools()
            assert len(tools) == 1

            user_tool = tools[0]
            assert user_tool.name == "get_user"

            # The parameter should be in the schema with its description
            assert "user_id" in user_tool.inputSchema.get("properties", {})
            assert user_tool.inputSchema["properties"]["user_id"]["description"] == "The user's unique identifier"

            # The description should only contain the summary, not parameter details
            assert user_tool.description == "Get user by ID"


@pytest.mark.asyncio
async def test_mixed_path_parameters_in_schema():
    """Test that when some path params are hidden, only visible ones appear in schema."""
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "0.1.0"},
        "paths": {
            "/api/{api_version}/users/{user_id}": {
                "get": {
                    "operationId": "get_versioned_user",
                    "summary": "Get user from specific API version",
                    "parameters": [
                        {
                            "name": "api_version",
                            "in": "path",
                            "required": True,
                            "description": "API version to use",
                            "schema": {
                                "type": "string"
                            }
                        },
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "description": "The user's unique identifier",
                            "schema": {
                                "type": "string"
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Success response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "name": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    async with httpx.AsyncClient(base_url="http://localhost:8000") as http_client:
        mcp = FastMCP.from_openapi(
            openapi_spec=openapi_spec,
            client=http_client,
        )

        # Hide api_version but not user_id
        mcp.add_transform(
            ToolTransform({
                "get_versioned_user": ToolTransformConfig(
                    arguments={
                        "api_version": ArgTransformConfig(
                            hide=True,
                            default="v1",
                        )
                    }
                )
            })
        )

        async with Client(mcp) as mcp_client:
            tools = await mcp_client.list_tools()
            assert len(tools) == 1

            tool = tools[0]
            assert tool.name == "get_versioned_user"

            # Only user_id should be in the schema
            assert "user_id" in tool.inputSchema.get("properties", {})
            assert "api_version" not in tool.inputSchema.get("properties", {})

            # The description should only contain the summary, not parameter details
            assert tool.description == "Get user from specific API version"
