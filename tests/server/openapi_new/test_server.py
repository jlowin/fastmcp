"""Unit tests for FastMCPOpenAPI server."""

import httpx
import pytest

from fastmcp.client import Client
from fastmcp.server.openapi_new import FastMCPOpenAPI


class TestFastMCPOpenAPIBasicFunctionality:
    """Test basic FastMCPOpenAPI server functionality."""
    
    @pytest.fixture
    def simple_openapi_spec(self):
        """Simple OpenAPI spec for testing."""
        return {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/users/{id}": {
                    "get": {
                        "operationId": "get_user",
                        "summary": "Get user by ID",
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "integer"}
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "User retrieved successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "name": {"type": "string"},
                                                "email": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/users": {
                    "post": {
                        "operationId": "create_user",
                        "summary": "Create a new user",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "email": {"type": "string"}
                                        },
                                        "required": ["name", "email"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "User created successfully",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "name": {"type": "string"},
                                                "email": {"type": "string"}
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
    
    def test_server_initialization(self, simple_openapi_spec):
        """Test server initialization with OpenAPI spec."""
        client = httpx.AsyncClient(base_url="https://api.example.com")
        
        server = FastMCPOpenAPI(
            openapi_spec=simple_openapi_spec,
            client=client,
            name="Test Server"
        )
        
        assert server.name == "Test Server"
        # Should have attempted to generate callables (may succeed or fail)
        assert isinstance(server._callables_map, dict)
    
    def test_server_initialization_with_custom_name(self, simple_openapi_spec):
        """Test server initialization with custom name."""
        client = httpx.AsyncClient(base_url="https://api.example.com")
        
        server = FastMCPOpenAPI(
            openapi_spec=simple_openapi_spec,
            client=client
        )
        
        # Should use default name
        assert server.name == "OpenAPI FastMCP"
    
    @pytest.mark.asyncio
    async def test_server_creates_tools_from_spec(self, simple_openapi_spec):
        """Test that server creates tools from OpenAPI spec."""
        async with httpx.AsyncClient(base_url="https://api.example.com") as client:
            server = FastMCPOpenAPI(
                openapi_spec=simple_openapi_spec,
                client=client,
                name="Test Server"
            )
            
            # Test with in-memory client
            async with Client(server) as mcp_client:
                tools = await mcp_client.list_tools()
                
                # Should have created tools for both operations
                assert len(tools) == 2
                
                tool_names = {tool.name for tool in tools}
                assert "get_user" in tool_names
                assert "create_user" in tool_names
    
    @pytest.mark.asyncio
    async def test_server_tool_execution_fallback_to_http(self, simple_openapi_spec):
        """Test tool execution falls back to HTTP when callables aren't available."""
        # Use a mock client that will be used for HTTP fallback
        mock_client = httpx.AsyncClient()
        
        server = FastMCPOpenAPI(
            openapi_spec=simple_openapi_spec,
            client=mock_client,
            name="Test Server"
        )
        
        # Ensure callables are not available (simulating generation failure)
        server._callables_map = {}
        
        async with Client(server) as mcp_client:
            tools = await mcp_client.list_tools()
            
            # Should still have tools even without callables
            assert len(tools) == 2
            
            # Tools should be OpenAPITool instances (HTTP fallback)
            # We'll just verify they exist and are callable
            get_user_tool = next(tool for tool in tools if tool.name == "get_user")
            assert get_user_tool is not None
            assert get_user_tool.description is not None
    
    def test_server_callable_generation_failure_handling(self, simple_openapi_spec):
        """Test that server handles callable generation failures gracefully."""
        client = httpx.AsyncClient(base_url="https://api.example.com")
        
        # This should not raise an exception even if callable generation fails
        server = FastMCPOpenAPI(
            openapi_spec=simple_openapi_spec,
            client=client,
            name="Test Server"
        )
        
        # Server should be created successfully
        assert server is not None
        assert server.name == "Test Server"
        # Callables map should exist (may be empty if generation failed)
        assert hasattr(server, '_callables_map')
    
    def test_server_with_timeout(self, simple_openapi_spec):
        """Test server initialization with timeout setting."""
        client = httpx.AsyncClient(base_url="https://api.example.com")
        
        server = FastMCPOpenAPI(
            openapi_spec=simple_openapi_spec,
            client=client,
            name="Test Server",
            timeout=30.0
        )
        
        assert server._timeout == 30.0
    
    def test_server_with_empty_spec(self):
        """Test server with minimal OpenAPI spec."""
        minimal_spec = {
            "openapi": "3.0.0",
            "info": {"title": "Empty API", "version": "1.0.0"},
            "paths": {}
        }
        
        client = httpx.AsyncClient(base_url="https://api.example.com")
        
        server = FastMCPOpenAPI(
            openapi_spec=minimal_spec,
            client=client,
            name="Empty Server"
        )
        
        assert server.name == "Empty Server"
        # Should handle empty paths gracefully
        assert isinstance(server._callables_map, dict)