import time
import unittest
import pytest
from fastmcp import FastMCP
from starlette.testclient import TestClient
from starlette import status

from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair

class TestToolManagementRoutes:
    @pytest.fixture
    def mcp(self):
        """Create a FastMCP server with test tools, resources, and prompts."""
        mcp = FastMCP("TestServer")

        # Add a test tool
        @mcp.tool
        def test_tool() -> str:
            """Test tool for tool management routes."""
            return "test_tool_result"

        # Add a test resource
        @mcp.resource("data://test_resource")
        def test_resource() -> str:
            """Test resource for tool management routes."""
            return "test_resource_result"

        # Add a test prompt
        @mcp.prompt
        def test_prompt() -> str:
            """Test prompt for tool management routes."""
            return "test_prompt_result"

        return mcp

    @pytest.fixture
    def client(self, mcp):
        """Create a test client for the FastMCP server."""
        return TestClient(mcp.http_app())

    def test_enable_tool_route(self, client, mcp):
        """Test enabling a tool via the HTTP route."""
        # First disable the tool
        tool = mcp._tool_manager.get_tool("test_tool")
        tool.enabled = False

        # Enable the tool via the HTTP route
        response = client.post("/tools/test_tool/enable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled tool: test_tool"}

        # Verify the tool is enabled
        tool = mcp._tool_manager.get_tool("test_tool")
        assert tool.enabled is True

    def test_disable_tool_route(self, client, mcp):
        """Test disabling a tool via the HTTP route."""
        # First ensure the tool is enabled
        tool = mcp._tool_manager.get_tool("test_tool")
        tool.enabled = True

        # Disable the tool via the HTTP route
        response = client.post("/tools/test_tool/disable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled tool: test_tool"}

        # Verify the tool is disabled
        tool = mcp._tool_manager.get_tool("test_tool")
        assert tool.enabled is False

    @pytest.mark.asyncio
    async def test_enable_resource_route(self, client, mcp):
        """Test enabling a resource via the HTTP route."""
        # First disable the resource
        resource = await mcp._resource_manager.get_resource("data://test_resource")
        resource.enabled = False

        # Enable the resource via the HTTP route
        response = client.post("/resources/data://test_resource/enable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled resource: data://test_resource"}

        # Verify the resource is enabled
        resource = await mcp._resource_manager.get_resource("data://test_resource")
        assert resource.enabled is True

    @pytest.mark.asyncio
    async def test_disable_resource_route(self, client, mcp):
        """Test disabling a resource via the HTTP route."""
        # First ensure the resource is enabled
        resource = await mcp._resource_manager.get_resource("data://test_resource")
        resource.enabled = True

        # Disable the resource via the HTTP route
        response = client.post("/resources/data://test_resource/disable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled resource: data://test_resource"}

        # Verify the resource is disabled
        resource = await mcp._resource_manager.get_resource("data://test_resource")
        assert resource.enabled is False

    def test_enable_prompt_route(self, client, mcp):
        """Test enabling a prompt via the HTTP route."""
        # First disable the prompt
        prompt = mcp._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = False

        # Enable the prompt via the HTTP route
        response = client.post("/prompts/test_prompt/enable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled prompt: test_prompt"}

        # Verify the prompt is enabled
        prompt = mcp._prompt_manager.get_prompt("test_prompt")
        assert prompt.enabled is True

    def test_disable_prompt_route(self, client, mcp):
        """Test disabling a prompt via the HTTP route."""
        # First ensure the prompt is enabled
        prompt = mcp._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = True

        # Disable the prompt via the HTTP route
        response = client.post("/prompts/test_prompt/disable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled prompt: test_prompt"}

        # Verify the prompt is disabled
        prompt = mcp._prompt_manager.get_prompt("test_prompt")
        assert prompt.enabled is False

    def test_enable_nonexistent_tool(self, client):
        """Test enabling a non-existent tool returns 404."""
        response = client.post("/tools/nonexistent_tool/enable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown tool: nonexistent_tool"

    def test_disable_nonexistent_tool(self, client):
        """Test disabling a non-existent tool returns 404."""
        response = client.post("/tools/nonexistent_tool/disable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown tool: nonexistent_tool"

    def test_enable_nonexistent_resource(self, client):
        """Test enabling a non-existent resource returns 404."""
        response = client.post("/resources/nonexistent_resource/enable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown resource: nonexistent_resource"

    def test_disable_nonexistent_resource(self, client):
        """Test disabling a non-existent resource returns 404."""
        response = client.post("/resources/nonexistent_resource/disable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown resource: nonexistent_resource"

    def test_enable_nonexistent_prompt(self, client):
        """Test enabling a non-existent prompt returns 404."""
        response = client.post("/prompts/nonexistent_prompt/enable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown prompt: nonexistent_prompt"

    def test_disable_nonexistent_prompt(self, client):
        """Test disabling a non-existent prompt returns 404."""
        response = client.post("/prompts/nonexistent_prompt/disable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown prompt: nonexistent_prompt"



class TestAuthToolManagement:
    """Test authentication requirements for tool management routes."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Generate a key pair and create an auth provider
        key_pair = RSAKeyPair.generate()
        self.auth = BearerAuthProvider(
            public_key=key_pair.public_key,
            issuer="https://dev.example.com",
            audience="my-dev-server"
        )
        self.mcp = FastMCP("TestServerWithAuth", auth=self.auth)
        self.token = key_pair.create_token(
            subject="dev-user",
            issuer="https://dev.example.com",
            audience="my-dev-server",
            scopes=["read", "write"]
        )
        
        # Add test components
        @self.mcp.tool
        def test_tool() -> str:
            """Test tool for auth testing."""
            return "test_tool_result"
            
        @self.mcp.resource("data://test_resource")
        def test_resource() -> str:
            """Test resource for auth testing."""
            return "test_resource_result"
            
        @self.mcp.prompt
        def test_prompt() -> str:
            """Test prompt for auth testing."""
            return "test_prompt_result"
        
        # Create test client
        self.client = TestClient(self.mcp.http_app())
        
    def test_unauthorized_enable_tool(self):
        """Test that unauthenticated requests to enable a tool are rejected."""
        tool = self.mcp._tool_manager.get_tool("test_tool")
        tool.enabled = False
        
        response = self.client.post("/tools/test_tool/enable")
        assert response.status_code == 401
        assert tool.enabled is False
    
    def test_authorized_enable_tool(self):
        """Test that authenticated requests to enable a tool are allowed."""
        tool = self.mcp._tool_manager.get_tool("test_tool")
        tool.enabled = False
        
        response = self.client.post(
            "/tools/test_tool/enable",
            headers={"Authorization": "Bearer " + self.token}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Enabled tool: test_tool"}
        assert tool.enabled is True
    
    def test_unauthorized_disable_tool(self):
        """Test that unauthenticated requests to disable a tool are rejected."""
        tool = self.mcp._tool_manager.get_tool("test_tool")
        tool.enabled = True
        
        response = self.client.post("/tools/test_tool/disable")
        assert response.status_code == 401
        assert tool.enabled is True
    
    def test_authorized_disable_tool(self):
        """Test that authenticated requests to disable a tool are allowed."""
        tool = self.mcp._tool_manager.get_tool("test_tool")
        tool.enabled = True
        
        response = self.client.post(
            "/tools/test_tool/disable",
            headers={"Authorization": "Bearer " + self.token}
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Disabled tool: test_tool"}
        assert tool.enabled is False
