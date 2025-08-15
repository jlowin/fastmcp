"""Tests for CLI run module with fastmcp.json support."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fastmcp.cli.run import parse_entrypoint, parse_file_path


class TestEntrypointParsing:
    """Test entrypoint parsing functionality."""

    def test_parse_simple_file(self):
        """Test parsing simple file path."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            file_path, obj_name, args = parse_entrypoint(str(temp_path))
            assert file_path == temp_path
            assert obj_name is None
            assert args == []
        finally:
            temp_path.unlink()

    def test_parse_file_with_object(self):
        """Test parsing file:object syntax."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            spec = f"{temp_path}:mcp"
            file_path, obj_name, args = parse_entrypoint(spec)
            assert file_path == temp_path
            assert obj_name == "mcp"
            assert args == []
        finally:
            temp_path.unlink()

    def test_parse_file_with_function_call(self):
        """Test parsing file:function() syntax."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            spec = f"{temp_path}:create_server()"
            file_path, obj_name, args = parse_entrypoint(spec)
            assert file_path == temp_path
            assert obj_name == "create_server"
            assert args == []
        finally:
            temp_path.unlink()

    def test_parse_module_path(self):
        """Test parsing module.path:object syntax."""
        # This test doesn't create actual module files
        spec = "myapp.server:create_app"
        file_path, obj_name, args = parse_entrypoint(spec)
        
        # Should convert to path form
        assert file_path == Path("myapp/server.py")
        assert obj_name == "create_app"
        assert args == []

    def test_parse_module_with_function_args(self):
        """Test parsing module:function(args) syntax."""
        spec = "myapp.factory:create_server(debug=True, port=8080)"
        file_path, obj_name, args = parse_entrypoint(spec)
        
        assert file_path == Path("myapp/factory.py")
        assert obj_name == "create_server"
        assert args == ["debug=True", "port=8080"]

    @pytest.mark.skipif(
        not Path("C:\\").exists(),
        reason="Windows path test only runs on Windows"
    )
    def test_parse_file_path_windows(self):
        """Test parsing Windows-style paths."""
        # Mock Windows path
        spec = "C:\\Users\\test\\server.py:mcp"
        
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                file_path, obj_name = parse_file_path(spec)
                
                # Should handle Windows drive letter correctly
                assert str(file_path).startswith("C:")
                assert obj_name == "mcp"


class TestConfigIntegration:
    """Test integration with fastmcp.json configuration."""

    @pytest.mark.asyncio
    async def test_run_with_fastmcp_json(self):
        """Test running with fastmcp.json configuration."""
        from fastmcp.cli.run import run_command
        
        # Create a temporary fastmcp.json
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "fastmcp.json"
            server_path = Path(tmpdir) / "server.py"
            
            # Create a simple server file
            server_path.write_text("""
from fastmcp import FastMCP

mcp = FastMCP("test-server")

@mcp.tool
def test_tool():
    return "test"
""")
            
            # Create config
            config_data = {
                "name": "test-server",
                "entrypoint": "server.py:mcp",
                "transport": "stdio",
                "log_level": "DEBUG",
            }
            with config_path.open("w") as f:
                json.dump(config_data, f)
            
            # Mock the server run to avoid actually starting it
            with patch("fastmcp.server.server.FastMCP.run_async") as mock_run:
                mock_run.return_value = None
                
                # Change to temp directory
                import os
                old_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    
                    # Run with no arguments should use fastmcp.json
                    await run_command()
                    
                    # Should have called run_async
                    mock_run.assert_called_once()
                    
                    # Check that log_level was applied
                    call_kwargs = mock_run.call_args.kwargs
                    assert call_kwargs.get("log_level") == "DEBUG"
                    
                finally:
                    os.chdir(old_cwd)

    @pytest.mark.asyncio 
    async def test_run_with_explicit_config_path(self):
        """Test running with explicit config path."""
        from fastmcp.cli.run import run_command
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "custom.json"
            server_path = Path(tmpdir) / "app.py"
            
            # Create server file
            server_path.write_text("""
from fastmcp import FastMCP

server = FastMCP("custom-server")
""")
            
            # Create config
            config_data = {
                "name": "custom-server",
                "entrypoint": str(server_path) + ":server",
                "transport": "http",
                "port": 9000,
            }
            with config_path.open("w") as f:
                json.dump(config_data, f)
            
            with patch("fastmcp.server.server.FastMCP.run_async") as mock_run:
                mock_run.return_value = None
                
                # Run with explicit config path
                await run_command(server_spec=str(config_path))
                
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args.kwargs
                assert call_kwargs.get("transport") == "http"
                assert call_kwargs.get("port") == 9000

    def test_run_with_uv_and_dependencies(self):
        """Test run_with_uv with dependencies from config."""
        from fastmcp.cli.run import run_with_uv
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "fastmcp.json"
            
            config_data = {
                "entrypoint": "server.py",
                "dependencies": ["httpx", "pydantic"],
                "python_version": "3.11",
                "transport": "http",
            }
            with config_path.open("w") as f:
                json.dump(config_data, f)
            
            # Mock subprocess.run
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                import os
                old_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    
                    # This should trigger SystemExit
                    with pytest.raises(SystemExit) as exc_info:
                        run_with_uv()
                    
                    assert exc_info.value.code == 0
                    
                    # Check the command that was run
                    mock_run.assert_called_once()
                    cmd = mock_run.call_args[0][0]
                    
                    # Should include dependencies
                    assert "--with" in cmd
                    httpx_idx = cmd.index("httpx")
                    assert cmd[httpx_idx - 1] == "--with"
                    
                    # Should include Python version
                    assert "--python" in cmd
                    py_idx = cmd.index("--python")
                    assert cmd[py_idx + 1] == "3.11"
                    
                finally:
                    os.chdir(old_cwd)