import pytest
from fastapi.testclient import TestClient
from starlette import status

from fastmcp import FastMCP


class TestToolManagementRoutes:
    @pytest.fixture
    def app(self):
        """Create a FastMCP server with test tools, resources, and prompts."""
        app = FastMCP("TestServer")

        # Add a test tool
        @app.tool
        def test_tool() -> str:
            """Test tool for tool management routes."""
            return "test_tool_result"

        # Add a test resource
        @app.resource("data://test_resource")
        def test_resource() -> str:
            """Test resource for tool management routes."""
            return "test_resource_result"

        # Add a test prompt
        @app.prompt
        def test_prompt() -> str:
            """Test prompt for tool management routes."""
            return "test_prompt_result"

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client for the FastMCP server."""
        return TestClient(app.http_app())

    def test_enable_tool_route(self, client, app):
        """Test enabling a tool via the HTTP route."""
        # First disable the tool
        tool = app._tool_manager.get_tool("test_tool")
        tool.enabled = False

        # Enable the tool via the HTTP route
        response = client.post("/tools/test_tool/enable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled tool: test_tool"}

        # Verify the tool is enabled
        tool = app._tool_manager.get_tool("test_tool")
        assert tool.enabled is True

    def test_disable_tool_route(self, client, app):
        """Test disabling a tool via the HTTP route."""
        # First ensure the tool is enabled
        tool = app._tool_manager.get_tool("test_tool")
        tool.enabled = True

        # Disable the tool via the HTTP route
        response = client.post("/tools/test_tool/disable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled tool: test_tool"}

        # Verify the tool is disabled
        tool = app._tool_manager.get_tool("test_tool")
        assert tool.enabled is False

    @pytest.mark.asyncio
    async def test_enable_resource_route(self, client, app):
        """Test enabling a resource via the HTTP route."""
        # First disable the resource
        resource = await app._resource_manager.get_resource("test_resource")
        resource.enabled = False

        # Enable the resource via the HTTP route
        response = client.post("/resources/test_resource/enable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled resource: test_resource"}

        # Verify the resource is enabled
        resource = await app._resource_manager.get_resource("test_resource")
        assert resource.enabled is True

    @pytest.mark.asyncio
    async def test_disable_resource_route(self, client, app):
        """Test disabling a resource via the HTTP route."""
        # First ensure the resource is enabled
        resource = await app._resource_manager.get_resource("test_resource")
        resource.enabled = True

        # Disable the resource via the HTTP route
        response = client.post("/resources/test_resource/disable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled resource: test_resource"}

        # Verify the resource is disabled
        resource = await app._resource_manager.get_resource("test_resource")
        assert resource.enabled is False

    def test_enable_prompt_route(self, client, app):
        """Test enabling a prompt via the HTTP route."""
        # First disable the prompt
        prompt = app._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = False

        # Enable the prompt via the HTTP route
        response = client.post("/prompts/test_prompt/enable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled prompt: test_prompt"}

        # Verify the prompt is enabled
        prompt = app._prompt_manager.get_prompt("test_prompt")
        assert prompt.enabled is True

    def test_disable_prompt_route(self, client, app):
        """Test disabling a prompt via the HTTP route."""
        # First ensure the prompt is enabled
        prompt = app._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = True

        # Disable the prompt via the HTTP route
        response = client.post("/prompts/test_prompt/disable")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled prompt: test_prompt"}

        # Verify the prompt is disabled
        prompt = app._prompt_manager.get_prompt("test_prompt")
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
