import pytest
from starlette import status
from starlette.testclient import TestClient

from fastmcp import FastMCP
from fastmcp.server.auth.providers.bearer import BearerAuthProvider, RSAKeyPair


class TestComponentManagementRoutes:
    """Test the component management routes for tools, resources, and prompts."""

    @pytest.fixture
    def mounted_mcp(self):
        """Create a FastMCP server with a mounted sub-server and a tool, resource, and prompt on the sub-server."""
        mounted_mcp = FastMCP("SubServer")

        @mounted_mcp.tool()
        def mounted_tool() -> str:
            return "mounted_tool_result"

        @mounted_mcp.resource("data://mounted_resource")
        def mounted_resource() -> str:
            return "mounted_resource_result"

        @mounted_mcp.prompt()
        def mounted_prompt() -> str:
            return "mounted_prompt_result"

        return mounted_mcp

    @pytest.fixture
    def mcp(self, mounted_mcp):
        """Create a FastMCP server with test tools, resources, and prompts."""
        mcp = FastMCP("TestServer")
        mcp.mount("sub", mounted_mcp)

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

    def test_enable_tool_route_on_mounted_server(self, client, mounted_mcp):
        """Test enabling a tool on a mounted server via the parent server's HTTP route."""
        # Disable the tool on the sub-server
        sub_tool = mounted_mcp._tool_manager.get_tool("mounted_tool")
        sub_tool.enabled = False
        # Enable via parent
        response = client.post("/tools/sub_mounted_tool/enable")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled tool: sub_mounted_tool"}
        # Confirm enabled on sub-server
        assert mounted_mcp._tool_manager.get_tool("mounted_tool").enabled is True

    @pytest.mark.asyncio
    async def test_enable_resource_route_on_mounted_server(self, client, mounted_mcp):
        """Test enabling a resource on a mounted server via the parent server's HTTP route."""
        resource = await mounted_mcp._resource_manager.get_resource(
            "data://mounted_resource"
        )
        resource.enabled = False
        response = client.post("/resources/data://sub/mounted_resource/enable")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "message": "Enabled resource: data://sub/mounted_resource"
        }
        resource = await mounted_mcp._resource_manager.get_resource(
            "data://mounted_resource"
        )
        assert resource.enabled is True

    def test_enable_prompt_route_on_mounted_server(self, client, mounted_mcp):
        """Test enabling a prompt on a mounted server via the parent server's HTTP route."""
        prompt = mounted_mcp._prompt_manager.get_prompt("mounted_prompt")
        prompt.enabled = False
        response = client.post("/prompts/sub_mounted_prompt/enable")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Enabled prompt: sub_mounted_prompt"}
        prompt = mounted_mcp._prompt_manager.get_prompt("mounted_prompt")
        assert prompt.enabled is True

    def test_disable_tool_route_on_mounted_server(self, client, mounted_mcp):
        """Test disabling a tool on a mounted server via the parent server's HTTP route."""
        # Enable the tool on the sub-server
        sub_tool = mounted_mcp._tool_manager.get_tool("mounted_tool")
        sub_tool.enabled = True
        # Disable via parent
        response = client.post("/tools/sub_mounted_tool/disable")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled tool: sub_mounted_tool"}
        # Confirm disabled on sub-server
        assert mounted_mcp._tool_manager.get_tool("mounted_tool").enabled is False

    @pytest.mark.asyncio
    async def test_disable_resource_route_on_mounted_server(self, client, mounted_mcp):
        """Test disabling a resource on a mounted server via the parent server's HTTP route."""
        resource = await mounted_mcp._resource_manager.get_resource(
            "data://mounted_resource"
        )
        resource.enabled = True
        response = client.post("/resources/data://sub/mounted_resource/disable")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "message": "Disabled resource: data://sub/mounted_resource"
        }
        resource = await mounted_mcp._resource_manager.get_resource(
            "data://mounted_resource"
        )
        assert resource.enabled is False

    def test_disable_prompt_route_on_mounted_server(self, client, mounted_mcp):
        """Test disabling a prompt on a mounted server via the parent server's HTTP route."""
        prompt = mounted_mcp._prompt_manager.get_prompt("mounted_prompt")
        prompt.enabled = True
        response = client.post("/prompts/sub_mounted_prompt/disable")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Disabled prompt: sub_mounted_prompt"}
        prompt = mounted_mcp._prompt_manager.get_prompt("mounted_prompt")
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
        response = client.post("/resources/nonexistent://resource/enable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown resource: nonexistent://resource"

    def test_disable_nonexistent_resource(self, client):
        """Test disabling a non-existent resource returns 404."""
        response = client.post("/resources/nonexistent://resource/disable")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.text == "Unknown resource: nonexistent://resource"

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


class TestAuthComponentManagementRoutes:
    """Test the component management routes with authentication for tools, resources, and prompts."""

    def setup_method(self):
        """Set up test fixtures."""
        # Generate a key pair and create an auth provider
        key_pair = RSAKeyPair.generate()
        self.auth = BearerAuthProvider(
            public_key=key_pair.public_key,
            issuer="https://dev.example.com",
            audience="my-dev-server",
        )
        self.mcp = FastMCP("TestServerWithAuth", auth=self.auth)
        self.token = key_pair.create_token(
            subject="dev-user",
            issuer="https://dev.example.com",
            audience="my-dev-server",
            scopes=["read", "write"],
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
            "/tools/test_tool/enable", headers={"Authorization": "Bearer " + self.token}
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
            headers={"Authorization": "Bearer " + self.token},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Disabled tool: test_tool"}
        assert tool.enabled is False

    @pytest.mark.asyncio
    async def test_unauthorized_enable_resource(self):
        """Test that unauthenticated requests to enable a resource are rejected."""
        resource = await self.mcp._resource_manager.get_resource("data://test_resource")
        resource.enabled = False

        response = self.client.post("/resources/data://test_resource/enable")
        assert response.status_code == 401
        assert resource.enabled is False

    @pytest.mark.asyncio
    async def test_authorized_enable_resource(self):
        """Test that authenticated requests to enable a resource are allowed."""
        resource = await self.mcp._resource_manager.get_resource("data://test_resource")
        resource.enabled = False

        response = self.client.post(
            "/resources/data://test_resource/enable",
            headers={"Authorization": "Bearer " + self.token},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Enabled resource: data://test_resource"}
        assert resource.enabled is True

    @pytest.mark.asyncio
    async def test_unauthorized_disable_resource(self):
        """Test that unauthenticated requests to disable a resource are rejected."""
        resource = await self.mcp._resource_manager.get_resource("data://test_resource")
        resource.enabled = True

        response = self.client.post("/resources/data://test_resource/disable")
        assert response.status_code == 401
        assert resource.enabled is True

    @pytest.mark.asyncio
    async def test_authorized_disable_resource(self):
        """Test that authenticated requests to disable a resource are allowed."""
        resource = await self.mcp._resource_manager.get_resource("data://test_resource")
        resource.enabled = True

        response = self.client.post(
            "/resources/data://test_resource/disable",
            headers={"Authorization": "Bearer " + self.token},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Disabled resource: data://test_resource"}
        assert resource.enabled is False

    def test_unauthorized_enable_prompt(self):
        """Test that unauthenticated requests to enable a prompt are rejected."""
        prompt = self.mcp._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = False

        response = self.client.post("/prompts/test_prompt/enable")
        assert response.status_code == 401
        assert prompt.enabled is False

    def test_authorized_enable_prompt(self):
        """Test that authenticated requests to enable a prompt are allowed."""
        prompt = self.mcp._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = False

        response = self.client.post(
            "/prompts/test_prompt/enable",
            headers={"Authorization": "Bearer " + self.token},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Enabled prompt: test_prompt"}
        assert prompt.enabled is True

    def test_unauthorized_disable_prompt(self):
        """Test that unauthenticated requests to disable a prompt are rejected."""
        prompt = self.mcp._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = True

        response = self.client.post("/prompts/test_prompt/disable")
        assert response.status_code == 401
        assert prompt.enabled is True

    def test_authorized_disable_prompt(self):
        """Test that authenticated requests to disable a prompt are allowed."""
        prompt = self.mcp._prompt_manager.get_prompt("test_prompt")
        prompt.enabled = True

        response = self.client.post(
            "/prompts/test_prompt/disable",
            headers={"Authorization": "Bearer " + self.token},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "Disabled prompt: test_prompt"}
        assert prompt.enabled is False
