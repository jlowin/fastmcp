"""Tests for FastMCP server configuration (fastmcp.json)."""

import json
import tempfile
from pathlib import Path

import pytest

from fastmcp.server.config import (
    FastMCPConfig,
    FastMCPServerConfig,
    create_default_config,
    load_fastmcp_config,
)


class TestFastMCPServerConfig:
    """Test FastMCPServerConfig model."""

    def test_minimal_config(self):
        """Test minimal configuration."""
        config = FastMCPServerConfig(entrypoint="server.py")
        assert config.entrypoint == "server.py"
        assert config.transport == "stdio"
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.log_level == "INFO"

    def test_full_config(self):
        """Test full configuration."""
        config = FastMCPServerConfig(
            name="test-server",
            version="2.0.0",
            entrypoint="myapp.server:create_app",
            dependencies=["httpx", "pydantic"],
            python_version=">=3.10",
            requirements_file=None,
            transport="http",
            host="0.0.0.0",
            port=8080,
            path="/api",
            env={"KEY": "value"},
            cwd="/app",
            timeout=5000,
            log_level="DEBUG",
            show_banner=False,
            auth_provider="bearer",
            auth_config={"token": "secret"},
            description="Test server",
            icon="icon.png",
        )
        
        assert config.name == "test-server"
        assert config.version == "2.0.0"
        assert config.entrypoint == "myapp.server:create_app"
        assert config.dependencies == ["httpx", "pydantic"]
        assert config.python_version == ">=3.10"
        assert config.transport == "http"
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.path == "/api"
        assert config.env == {"KEY": "value"}
        assert config.cwd == "/app"
        assert config.timeout == 5000
        assert config.log_level == "DEBUG"
        assert config.show_banner is False
        assert config.auth_provider == "bearer"
        assert config.auth_config == {"token": "secret"}
        assert config.description == "Test server"
        assert config.icon == "icon.png"

    def test_to_cli_args(self):
        """Test conversion to CLI arguments."""
        config = FastMCPServerConfig(
            entrypoint="server.py",
            transport="http",
            host="0.0.0.0",
            port=9000,
            path="/test",
            log_level="DEBUG",
            show_banner=False,
        )
        
        args = config.to_cli_args()
        assert "--transport" in args
        assert "http" in args
        assert "--host" in args
        assert "0.0.0.0" in args
        assert "--port" in args
        assert "9000" in args
        assert "--path" in args
        assert "/test" in args
        assert "--log-level" in args
        assert "DEBUG" in args
        assert "--no-banner" in args

    def test_get_dependencies_args(self):
        """Test getting dependency arguments."""
        config = FastMCPServerConfig(
            entrypoint="server.py",
            dependencies=["httpx", "pydantic"],
            python_version="3.11",
        )
        
        dep_args = config.get_dependencies_args()
        assert dep_args["with_packages"] == ["httpx", "pydantic"]
        assert dep_args["python_version"] == "3.11"


class TestFastMCPConfig:
    """Test FastMCPConfig root configuration."""

    def test_single_server_config(self):
        """Test single server configuration."""
        config_data = {
            "name": "my-server",
            "entrypoint": "server.py:mcp",
            "transport": "http",
        }
        
        config = FastMCPConfig.from_file(self._create_temp_json(config_data))
        assert config is not None
        assert config.servers is not None
        assert "default" in config.servers
        assert config.default == "default"
        
        server_config = config.get_server_config()
        assert server_config is not None
        assert server_config.name == "my-server"
        assert server_config.entrypoint == "server.py:mcp"
        assert server_config.transport == "http"

    def test_multi_server_config(self):
        """Test multi-server configuration."""
        config_data = {
            "servers": {
                "main": {
                    "entrypoint": "main.py",
                    "transport": "http",
                },
                "worker": {
                    "entrypoint": "worker.py",
                    "transport": "stdio",
                },
            },
            "default": "main",
        }
        
        config = FastMCPConfig.from_file(self._create_temp_json(config_data))
        assert config is not None
        assert config.servers is not None
        assert "main" in config.servers
        assert "worker" in config.servers
        assert config.default == "main"
        
        # Get default server
        main_config = config.get_server_config()
        assert main_config is not None
        assert main_config.entrypoint == "main.py"
        assert main_config.transport == "http"
        
        # Get specific server
        worker_config = config.get_server_config("worker")
        assert worker_config is not None
        assert worker_config.entrypoint == "worker.py"
        assert worker_config.transport == "stdio"

    def test_write_to_file(self):
        """Test writing configuration to file."""
        config = FastMCPConfig(
            servers={
                "test": FastMCPServerConfig(
                    entrypoint="test.py",
                    transport="http",
                )
            },
            default="test",
        )
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            config.write_to_file(temp_path)
            
            # Read back and verify
            with temp_path.open() as f:
                data = json.load(f)
            
            # Should write single server in simplified format
            assert "entrypoint" in data
            assert data["entrypoint"] == "test.py"
            assert data["transport"] == "http"
        finally:
            temp_path.unlink()

    def test_nonexistent_file(self):
        """Test loading from nonexistent file."""
        config = FastMCPConfig.from_file(Path("/nonexistent/file.json"))
        assert config is None

    def _create_temp_json(self, data: dict) -> Path:
        """Create a temporary JSON file with data."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            return Path(f.name)


class TestConfigLoading:
    """Test configuration loading functions."""

    def test_load_fastmcp_config_default(self):
        """Test loading default fastmcp.json."""
        # Create fastmcp.json in temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "fastmcp.json"
            config_data = {
                "name": "test",
                "entrypoint": "server.py",
            }
            with config_path.open("w") as f:
                json.dump(config_data, f)
            
            # Change to temp directory
            import os
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                config = load_fastmcp_config()
                assert config is not None
                assert config.name == "test"
                assert config.entrypoint == "server.py"
            finally:
                os.chdir(old_cwd)

    def test_load_fastmcp_config_explicit_path(self):
        """Test loading from explicit path."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            config_data = {
                "name": "explicit",
                "entrypoint": "app.py",
            }
            json.dump(config_data, f)
            temp_path = Path(f.name)
        
        try:
            config = load_fastmcp_config(temp_path)
            assert config is not None
            assert config.name == "explicit"
            assert config.entrypoint == "app.py"
        finally:
            temp_path.unlink()

    def test_create_default_config(self):
        """Test creating default configuration."""
        config = create_default_config()
        assert config.name == "my-server"
        assert config.entrypoint == "server.py:mcp"
        assert config.transport == "stdio"
        
        config = create_default_config(
            entrypoint="custom.py",
            name="custom-server",
            transport="http",
        )
        assert config.name == "custom-server"
        assert config.entrypoint == "custom.py"
        assert config.transport == "http"