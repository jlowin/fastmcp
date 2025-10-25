from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from fastmcp.cli.install.continue_client import (
    continue_command,
    convert_env_to_continue_format,
    get_continue_mcp_servers_dir,
    install_continue,
)


class TestContinueClientDirectories:
    """Test Continue directory handling."""

    def test_get_continue_mcp_servers_dir(self):
        """Test getting the Continue mcpServers directory path."""
        mcp_dir = get_continue_mcp_servers_dir()
        assert mcp_dir == Path.home() / ".continue" / "mcpServers"


class TestEnvConversion:
    """Test environment variable conversion."""

    def test_convert_env_to_continue_format_none(self):
        """Test conversion with None env vars."""
        result = convert_env_to_continue_format(None)
        assert result is None

    def test_convert_env_to_continue_format_empty(self):
        """Test conversion with empty env vars."""
        result = convert_env_to_continue_format({})
        # Empty dict is treated as None to match Continue's schema
        assert result is None

    def test_convert_env_to_continue_format_with_values(self):
        """Test conversion with actual env vars."""
        env_vars = {"API_KEY": "test-key", "DEBUG": "true"}
        result = convert_env_to_continue_format(env_vars)
        assert result == env_vars


class TestInstallContinueClient:
    """Test Continue client installation functionality."""

    def test_install_continue_success(self, tmp_path):
        """Test successful Continue client installation."""
        # Mock the home directory
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
            )

            assert result is True

            # Verify the YAML file was created
            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            assert config_file.exists()

            # Verify the YAML content follows Continue block schema
            with open(config_file) as f:
                yaml_content = yaml.safe_load(f)

            # Block metadata
            assert yaml_content["name"] == "test-server"
            assert yaml_content["version"] == "0.0.1"
            assert yaml_content["schema"] == "v1"
            assert "mcpServers" in yaml_content
            assert isinstance(yaml_content["mcpServers"], list)
            assert len(yaml_content["mcpServers"]) == 1
            
            # Server config within mcpServers array
            server_config = yaml_content["mcpServers"][0]
            assert server_config["name"] == "test-server"
            assert server_config["type"] == "stdio"
            assert server_config["command"] == "uv"
            assert "args" in server_config
            assert "run" in server_config["args"]
            assert "fastmcp" in server_config["args"]
            assert "/path/to/server.py" in " ".join(server_config["args"])

    def test_install_continue_with_packages(self, tmp_path):
        """Test Continue client installation with additional packages."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object="app",
                name="test-server",
                with_packages=["numpy", "pandas"],
                env_vars={"API_KEY": "test"},
            )

            assert result is True

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            with open(config_file) as f:
                yaml_content = yaml.safe_load(f)

            server_config = yaml_content["mcpServers"][0]
            # Check that all packages are included
            assert server_config["name"] == "test-server"
            assert server_config["type"] == "stdio"
            args_str = " ".join(server_config["args"])
            assert "--with" in args_str
            assert "numpy" in args_str
            assert "pandas" in args_str
            assert "fastmcp" in args_str
            assert "server.py:app" in args_str
            assert server_config["env"] == {"API_KEY": "test"}

    def test_install_continue_with_editable(self, tmp_path):
        """Test Continue client installation with editable package."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        editable_path = Path.cwd() / "local" / "package"

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object="custom_app",
                name="test-server",
                with_editable=[editable_path],
            )

            assert result is True

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            with open(config_file) as f:
                yaml_content = yaml.safe_load(f)

            server_config = yaml_content["mcpServers"][0]
            assert "--with-editable" in server_config["args"]
            # Check that the path was resolved (should be absolute)
            editable_idx = server_config["args"].index("--with-editable") + 1
            resolved_path = server_config["args"][editable_idx]
            assert Path(resolved_path).is_absolute()
            assert "server.py:custom_app" in " ".join(server_config["args"])

    def test_install_continue_with_python_version(self, tmp_path):
        """Test Continue client installation with specific Python version."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
                python_version="3.11",
            )

            assert result is True

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            with open(config_file) as f:
                yaml_content = yaml.safe_load(f)

            server_config = yaml_content["mcpServers"][0]
            assert "--python" in server_config["args"]
            assert "3.11" in server_config["args"]

    def test_install_continue_with_requirements(self, tmp_path):
        """Test Continue client installation with requirements file."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        requirements_file = tmp_path / "requirements.txt"
        requirements_file.write_text("numpy\npandas\n")

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
                with_requirements=requirements_file,
            )

            assert result is True

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            with open(config_file) as f:
                yaml_content = yaml.safe_load(f)

            server_config = yaml_content["mcpServers"][0]
            assert "--with-requirements" in server_config["args"]
            assert str(requirements_file) in server_config["args"]

    def test_install_continue_with_project(self, tmp_path):
        """Test Continue client installation with project directory."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
                project=project_dir,
            )

            assert result is True

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            with open(config_file) as f:
                yaml_content = yaml.safe_load(f)

            server_config = yaml_content["mcpServers"][0]
            # Project is passed to uv command args
            assert "--project" in server_config["args"]
            assert str(project_dir) in server_config["args"]
            # And also set as cwd in the YAML config
            assert server_config["cwd"] == str(project_dir)

    def test_install_continue_yaml_format(self, tmp_path):
        """Test that the YAML file follows Continue's block schema."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
            )

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"

            # Verify it's valid YAML following Continue block schema
            yaml_data = yaml.safe_load(config_file.read_text())
            assert isinstance(yaml_data, dict)
            
            # Block metadata fields
            assert "name" in yaml_data
            assert yaml_data["name"] == "test-server"
            assert "version" in yaml_data
            assert "schema" in yaml_data
            assert "mcpServers" in yaml_data
            assert isinstance(yaml_data["mcpServers"], list)
            assert len(yaml_data["mcpServers"]) == 1
            
            # Server config within mcpServers array
            server_config = yaml_data["mcpServers"][0]
            assert "name" in server_config
            assert server_config["name"] == "test-server"
            assert "type" in server_config
            assert server_config["type"] == "stdio"
            assert "command" in server_config
            assert server_config["command"] == "uv"
            
            # Optional fields
            if "args" in server_config:
                assert isinstance(server_config["args"], list)
            if "env" in server_config:
                assert isinstance(server_config["env"], dict)

    def test_install_continue_creates_directory(self, tmp_path):
        """Test that installation creates the mcpServers directory if it doesn't exist."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        mcp_servers_dir = mock_home / ".continue" / "mcpServers"
        assert not mcp_servers_dir.exists()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            result = install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
            )

            assert result is True
            assert mcp_servers_dir.exists()
            assert mcp_servers_dir.is_dir()

    def test_install_continue_no_env_no_cwd(self, tmp_path):
        """Test that env and cwd are not included when not provided."""
        mock_home = tmp_path / "mock_home"
        mock_home.mkdir()

        with patch("fastmcp.cli.install.continue_client.Path.home", return_value=mock_home):
            install_continue(
                file=Path("/path/to/server.py"),
                server_object=None,
                name="test-server",
            )

            config_file = mock_home / ".continue" / "mcpServers" / "test-server.yaml"
            yaml_data = yaml.safe_load(config_file.read_text())
            server_config = yaml_data["mcpServers"][0]
            
            # Optional fields should not be present when not provided
            assert "env" not in server_config
            assert "cwd" not in server_config


class TestContinueClientCommand:
    """Test the Continue client CLI command."""

    @patch("fastmcp.cli.install.continue_client.install_continue")
    @patch("fastmcp.cli.install.continue_client.process_common_args")
    async def test_continue_command_basic(self, mock_process_args, mock_install):
        """Test basic Continue client command execution."""
        mock_process_args.return_value = (
            Path("server.py"),
            None,
            "test-server",
            [],
            {},
        )
        mock_install.return_value = True

        with patch("sys.exit") as mock_exit:
            await continue_command("server.py")

        mock_install.assert_called_once_with(
            file=Path("server.py"),
            server_object=None,
            name="test-server",
            with_editable=[],
            with_packages=[],
            env_vars={},
            python_version=None,
            with_requirements=None,
            project=None,
        )
        mock_exit.assert_not_called()

    @patch("fastmcp.cli.install.continue_client.install_continue")
    @patch("fastmcp.cli.install.continue_client.process_common_args")
    async def test_continue_command_with_options(self, mock_process_args, mock_install):
        """Test Continue client command with all options."""
        mock_process_args.return_value = (
            Path("server.py"),
            "app",
            "my-server",
            ["numpy"],
            {"API_KEY": "test"},
        )
        mock_install.return_value = True

        await continue_command(
            "server.py",
            server_name="my-server",
            with_packages=["numpy"],
            env_vars=["API_KEY=test"],
            python="3.11",
        )

        mock_install.assert_called_once()
        call_kwargs = mock_install.call_args[1]
        assert call_kwargs["python_version"] == "3.11"

    @patch("fastmcp.cli.install.continue_client.install_continue")
    @patch("fastmcp.cli.install.continue_client.process_common_args")
    async def test_continue_command_failure(self, mock_process_args, mock_install):
        """Test Continue client command when installation fails."""
        mock_process_args.return_value = (
            Path("server.py"),
            None,
            "test-server",
            [],
            {},
        )
        mock_install.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            await continue_command("server.py")

        assert isinstance(exc_info.value, SystemExit)
        assert exc_info.value.code == 1
        assert exc_info.value.code == 1
