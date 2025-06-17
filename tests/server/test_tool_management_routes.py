import pytest
from fastapi.testclient import TestClient
from starlette import status

from fastmcp import FastMCP


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
