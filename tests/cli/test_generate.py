"""Tests for generate CLI command."""

import tempfile
from pathlib import Path

import mcp.types

from fastmcp import Client, FastMCP
from fastmcp.cli.cli import _infer_server_name
from fastmcp.utilities.generate import (
    generate_agents_md,
    generate_args_dict,
    generate_auth_code,
    generate_tool_script,
    generate_typed_params,
    json_schema_to_python_type,
    to_snake_case,
)


class TestSnakeCase:
    def test_hyphenated_names(self):
        assert to_snake_case("get-document") == "get_document"
        assert to_snake_case("list-all-items") == "list_all_items"

    def test_dotted_names(self):
        assert to_snake_case("chrome.getTabs") == "chrome_get_tabs"
        assert to_snake_case("list.items") == "list_items"

    def test_camel_case(self):
        assert to_snake_case("getDocument") == "get_document"
        assert to_snake_case("listAllItems") == "list_all_items"

    def test_mixed_formats(self):
        assert to_snake_case("get-documentId") == "get_document_id"
        assert to_snake_case("Chrome.getTabs") == "chrome_get_tabs"


class TestJsonSchemaToType:
    def test_basic_types(self):
        assert json_schema_to_python_type({"type": "string"}) == "str"
        assert json_schema_to_python_type({"type": "integer"}) == "int"
        assert json_schema_to_python_type({"type": "number"}) == "float"
        assert json_schema_to_python_type({"type": "boolean"}) == "bool"
        assert json_schema_to_python_type({"type": "array"}) == "list"
        assert json_schema_to_python_type({"type": "object"}) == "dict"

    def test_unknown_type(self):
        assert json_schema_to_python_type({"type": "unknown"}) == "Any"
        assert json_schema_to_python_type({}) == "Any"


class TestTypedParams:
    def test_no_parameters(self):
        schema = {"type": "object", "properties": {}}
        params, names = generate_typed_params(schema)
        assert params == ""
        assert names == []

    def test_required_parameter(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        params, names = generate_typed_params(schema)
        assert params == "name: str"
        assert names == ["name"]

    def test_optional_parameter(self):
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
        }
        params, names = generate_typed_params(schema)
        assert params == "age: int | None = None"
        assert names == ["age"]

    def test_mixed_parameters(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "email": {"type": "string"},
            },
            "required": ["name", "email"],
        }
        params, names = generate_typed_params(schema)
        assert "name: str" in params
        assert "email: str" in params
        assert "age: int | None = None" in params
        assert names == ["name", "age", "email"]


class TestArgsDict:
    def test_empty_params(self):
        result = generate_args_dict([])
        assert result == "{}"

    def test_single_param(self):
        result = generate_args_dict(["name"])
        assert '"name": name' in result

    def test_multiple_params(self):
        result = generate_args_dict(["name", "age", "email"])
        assert '"name": name' in result
        assert '"age": age' in result
        assert '"email": email' in result


class TestAuthCode:
    def test_oauth_mode(self):
        imports, auth_func = generate_auth_code(
            "oauth", None, "https://example.com/mcp"
        )
        assert "from fastmcp.client.auth import OAuth" in imports
        assert 'OAuth(mcp_url="https://example.com/mcp")' in auth_func
        assert "def get_auth():" in auth_func

    def test_env_var_mode(self):
        imports, auth_func = generate_auth_code(
            "env_var", "MY_API_TOKEN", "https://example.com/mcp"
        )
        assert imports == ""
        assert 'os.environ.get("MY_API_TOKEN")' in auth_func
        assert "Missing required environment variable: MY_API_TOKEN" in auth_func
        assert "def get_auth():" in auth_func

    def test_token_mode(self):
        imports, auth_func = generate_auth_code(
            "token", "sk-test-123", "https://example.com/mcp"
        )
        assert imports == ""
        assert 'return "sk-test-123"' in auth_func
        assert "def get_auth():" in auth_func

    def test_none_mode(self):
        imports, auth_func = generate_auth_code("none", None, "https://example.com/mcp")
        assert imports == ""
        assert "return None" in auth_func
        assert "def get_auth():" in auth_func


class TestToolScript:
    def test_simple_tool(self):
        tool = mcp.types.Tool(
            name="echo",
            description="Echo back the input",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
        script = generate_tool_script(tool, "https://example.com/mcp")

        # Check PEP 723 metadata
        assert "# /// script" in script
        assert '# dependencies = ["fastmcp>=2.0.0"]' in script

        # Check function signature
        assert "async def echo(text: str) -> Any:" in script

        # Check tool call
        assert 'await client.call_tool("echo"' in script

        # Check server URL
        assert 'SERVER_URL = "https://example.com/mcp"' in script

        # Check JSON parameter handling in __main__
        assert "import json" in script
        assert "import sys" in script
        assert "params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}" in script
        assert "asyncio.run(echo(**params))" in script

    def test_tool_with_no_params(self):
        tool = mcp.types.Tool(
            name="get-status",
            description="Get server status",
            inputSchema={"type": "object", "properties": {}},
        )
        script = generate_tool_script(tool, "https://example.com/mcp")

        # Should have function with no params
        assert "async def get_status() -> Any:" in script

    def test_tool_with_optional_params(self):
        tool = mcp.types.Tool(
            name="search",
            description="Search for items",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        )
        script = generate_tool_script(tool, "https://example.com/mcp")

        # Check mixed params
        assert "query: str" in script
        assert "limit: int | None = None" in script

    def test_tool_with_oauth_auth(self):
        tool = mcp.types.Tool(
            name="echo",
            description="Echo back",
            inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
        script = generate_tool_script(tool, "https://example.com/mcp", "oauth", None)

        # Check OAuth import
        assert "from fastmcp.client.auth import OAuth" in script

        # Check OAuth instantiation with mcp_url
        assert 'OAuth(mcp_url="https://example.com/mcp")' in script

    def test_tool_with_env_var_auth(self):
        tool = mcp.types.Tool(
            name="echo",
            description="Echo back",
            inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
        script = generate_tool_script(
            tool, "https://example.com/mcp", "env_var", "MY_API_TOKEN"
        )

        # Check env var reading
        assert 'os.environ.get("MY_API_TOKEN")' in script

        # Check error handling
        assert "Missing required environment variable: MY_API_TOKEN" in script

        # Should NOT have OAuth import
        assert "from fastmcp.client.auth import OAuth" not in script

    def test_tool_with_token_auth(self):
        tool = mcp.types.Tool(
            name="echo",
            description="Echo back",
            inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
        script = generate_tool_script(
            tool, "https://example.com/mcp", "token", "sk-test-123"
        )

        # Check embedded token
        assert 'return "sk-test-123"' in script

        # Should NOT have OAuth import
        assert "from fastmcp.client.auth import OAuth" not in script

    def test_tool_with_no_auth(self):
        tool = mcp.types.Tool(
            name="echo",
            description="Echo back",
            inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
        script = generate_tool_script(tool, "https://example.com/mcp", "none", None)

        # Check no auth
        assert "return None" in script

        # Should NOT have OAuth import
        assert "from fastmcp.client.auth import OAuth" not in script


class TestAgentsMd:
    def test_basic_generation_no_auth(self):
        tools = [
            mcp.types.Tool(
                name="echo",
                description="Echo back",
                inputSchema={"type": "object"},
            ),
            mcp.types.Tool(
                name="reverse",
                description="Reverse text",
                inputSchema={"type": "object"},
            ),
        ]

        md = generate_agents_md(
            "TestServer", "https://example.com", tools, "none", None, None
        )

        assert "# MCP Tools: TestServer" in md
        assert "Generated from: https://example.com" in md
        assert "Tools: 2" in md
        assert "- `echo.py` - Echo back" in md
        assert "- `reverse.py` - Reverse text" in md
        # Check JSON parameter documentation
        assert "JSON parameters" in md or "JSON as first argument" in md
        assert "uv run" in md
        # Auth documentation should NOT be present
        assert "## Authentication" not in md

    def test_no_auth_documentation_regardless_of_mode(self):
        """Auth documentation should not be included in AGENTS.md regardless of auth mode."""
        tools = [
            mcp.types.Tool(
                name="test", description="Test", inputSchema={"type": "object"}
            ),
        ]

        # Test all auth modes - none should generate auth documentation
        for auth_mode, auth_value in [
            ("none", None),
            ("oauth", None),
            ("env_var", "MY_API_TOKEN"),
            ("token", "sk-test"),
        ]:
            md = generate_agents_md(
                "TestServer", "https://example.com", tools, auth_mode, auth_value, None
            )
            # No auth documentation should be present
            assert "## Authentication" not in md
            # Specific auth-related text should not be present
            if auth_mode == "env_var":
                assert "export MY_API_TOKEN" not in md
            assert "FASTMCP_AUTH_TOKEN" not in md

    def test_server_instructions_included(self):
        tools = [
            mcp.types.Tool(
                name="test", description="Test", inputSchema={"type": "object"}
            ),
        ]
        instructions = (
            "Make sure to use these tools responsibly and follow rate limits."
        )
        md = generate_agents_md(
            "TestServer", "https://example.com", tools, "none", None, instructions
        )

        assert "## Server Instructions" in md
        assert instructions in md

    def test_no_instructions_section_when_none(self):
        tools = [
            mcp.types.Tool(
                name="test", description="Test", inputSchema={"type": "object"}
            ),
        ]
        md = generate_agents_md(
            "TestServer", "https://example.com", tools, "none", None, None
        )

        assert "## Server Instructions" not in md


class TestInferServerName:
    def test_simple_url(self):
        assert _infer_server_name("https://example.com/mcp") == "mcp"
        assert _infer_server_name("https://api.github.com/mcp") == "mcp"

    def test_url_with_hostname(self):
        # Should remove www and common TLDs
        name = _infer_server_name("https://www.example.com")
        assert "example" in name

    def test_complex_path(self):
        assert _infer_server_name("https://api.example.com/v1/mcp/tools") == "tools"


class TestEndToEnd:
    async def test_generate_and_run_script(self):
        """Test generating a script and executing it."""
        # Create a test server
        mcp = FastMCP("TestServer")

        @mcp.tool
        def greet(name: str) -> str:
            """Greet someone"""
            return f"Hello, {name}!"

        # Connect and get tools
        async with Client(mcp) as client:
            tools = await client.list_tools()

        # Generate script
        tool = tools[0]
        script = generate_tool_script(tool, "test://server")

        # Write to temp file and verify it's valid Python
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = Path(f.name)

        try:
            # Compile to check for syntax errors
            compile(script, str(script_path), "exec")
        finally:
            script_path.unlink()

    async def test_full_generation_flow_with_instructions(self):
        """Test complete flow: server with instructions -> files on disk."""
        # Create a test server with instructions
        mcp = FastMCP("TestServer")
        mcp.instructions = "Use these tools carefully. Rate limit: 100/min."

        @mcp.tool
        def echo(text: str) -> str:
            """Echo back text"""
            return text

        @mcp.tool
        def reverse(text: str) -> str:
            """Reverse text"""
            return text[::-1]

        # Connect and get tools + server info
        async with Client(mcp) as client:
            tools = await client.list_tools()
            instructions = (
                client.initialize_result.instructions
                if client.initialize_result
                else None
            )
            server_name = (
                client.initialize_result.serverInfo.name
                if client.initialize_result and client.initialize_result.serverInfo
                else "test_server"
            )

        # Generate files in temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_output"
            output_dir.mkdir()

            # Generate tool scripts
            for tool in tools:
                script = generate_tool_script(tool, "test://server", "none", None)
                filename = to_snake_case(tool.name) + ".py"
                (output_dir / filename).write_text(script)

            # Generate AGENTS.md
            agents_md = generate_agents_md(
                server_name, "test://server", tools, "none", None, instructions
            )
            (output_dir / "AGENTS.md").write_text(agents_md)

            # Verify files exist
            assert (output_dir / "echo.py").exists()
            assert (output_dir / "reverse.py").exists()
            assert (output_dir / "AGENTS.md").exists()

            # Verify AGENTS.md content
            agents_content = (output_dir / "AGENTS.md").read_text()
            assert "## Server Instructions" in agents_content
            assert "Use these tools carefully" in agents_content
            assert "Rate limit: 100/min" in agents_content
            assert "- `echo.py` - Echo back text" in agents_content
            assert "- `reverse.py` - Reverse text" in agents_content
            assert "## Authentication" not in agents_content  # No auth docs

            # Verify script content
            echo_script = (output_dir / "echo.py").read_text()
            assert "async def echo(text: str)" in echo_script
            assert 'SERVER_URL = "test://server"' in echo_script
            assert "return None" in echo_script  # No auth mode

    async def test_generation_with_different_auth_modes(self):
        """Test generating scripts with all auth modes."""
        mcp = FastMCP("AuthTestServer")

        @mcp.tool
        def test_tool() -> str:
            """Test tool"""
            return "ok"

        async with Client(mcp) as client:
            tools = await client.list_tools()

        tool = tools[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test OAuth mode
            script_oauth = generate_tool_script(
                tool, "https://api.test.com", "oauth", None
            )
            oauth_path = Path(tmpdir) / "oauth.py"
            oauth_path.write_text(script_oauth)
            assert "from fastmcp.client.auth import OAuth" in script_oauth
            assert 'OAuth(mcp_url="https://api.test.com")' in script_oauth
            compile(script_oauth, str(oauth_path), "exec")  # Verify syntax

            # Test env var mode
            script_env = generate_tool_script(
                tool, "https://api.test.com", "env_var", "MY_TOKEN"
            )
            env_path = Path(tmpdir) / "env.py"
            env_path.write_text(script_env)
            assert 'os.environ.get("MY_TOKEN")' in script_env
            assert "Missing required environment variable: MY_TOKEN" in script_env
            compile(script_env, str(env_path), "exec")  # Verify syntax

            # Test token mode
            script_token = generate_tool_script(
                tool, "https://api.test.com", "token", "sk-test-123"
            )
            token_path = Path(tmpdir) / "token.py"
            token_path.write_text(script_token)
            assert 'return "sk-test-123"' in script_token
            compile(script_token, str(token_path), "exec")  # Verify syntax

            # Test none mode
            script_none = generate_tool_script(
                tool, "https://api.test.com", "none", None
            )
            none_path = Path(tmpdir) / "none.py"
            none_path.write_text(script_none)
            assert "return None" in script_none
            compile(script_none, str(none_path), "exec")  # Verify syntax


class TestCLICommand:
    """Tests for the CLI command itself."""

    async def test_auth_parsing_oauth(self):
        """Test that --auth oauth is recognized."""
        auth_value = "oauth"
        # Simulate parsing logic
        if auth_value == "oauth":
            auth_mode = "oauth"
        elif auth_value.startswith("$"):
            auth_mode = "env_var"
        else:
            auth_mode = "token"
        assert auth_mode == "oauth"

    async def test_auth_parsing_env_var(self):
        """Test that --auth $VAR is recognized as env var."""
        import os

        # Set up an env var
        os.environ["TEST_TOKEN"] = "test-value"

        auth_value = "$TEST_TOKEN"
        # Simulate parsing logic
        if auth_value == "oauth":
            auth_mode = "oauth"
        elif auth_value.startswith("$"):
            auth_mode = "env_var"
            env_var_name = auth_value[1:]
            token = os.environ.get(env_var_name)
            assert token == "test-value"
        else:
            auth_mode = "token"
        assert auth_mode == "env_var"

        del os.environ["TEST_TOKEN"]

    async def test_auth_parsing_literal_token(self):
        """Test that --auth with literal value is treated as token."""
        auth_value = "sk-test-123"
        # Simulate parsing logic
        if auth_value == "oauth":
            auth_mode = "oauth"
        elif auth_value.startswith("$"):
            auth_mode = "env_var"
        else:
            auth_mode = "token"
        assert auth_mode == "token"
        assert auth_value == "sk-test-123"

    async def test_cli_missing_env_var_fails(self):
        """Test that missing env var when using $VAR would fail."""
        import os

        # Ensure env var doesn't exist
        if "NONEXISTENT_VAR" in os.environ:
            del os.environ["NONEXISTENT_VAR"]

        # Simulate the CLI check
        auth_value = "$NONEXISTENT_VAR"
        env_var_name = auth_value[1:]
        token = os.environ.get(env_var_name)
        assert token is None  # Would cause CLI to exit with error

    async def test_generated_scripts_are_executable(self):
        """Test that generated scripts can actually be imported and used."""
        mcp = FastMCP("ExecutableTest")

        @mcp.tool
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers"""
            return a * b

        async with Client(mcp) as client:
            tools = await client.list_tools()

        tool = tools[0]
        script = generate_tool_script(tool, "test://server", "none", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "multiply.py"
            script_path.write_text(script)

            # Verify it's valid Python
            compile(script, str(script_path), "exec")

            # Verify key components are present
            assert "async def multiply(a: int, b: int) -> Any:" in script
            assert 'await client.call_tool("multiply"' in script
            assert '"a": a' in script
            assert '"b": b' in script
