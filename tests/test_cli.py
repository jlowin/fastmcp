"""Tests for the FastMCP CLI."""

import json
from pathlib import Path
from unittest.mock import patch, call

import pytest
from typer.testing import CliRunner

from fastmcp.cli.cli import app, _parse_env_var, _parse_file_path


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock Claude config file."""
    config = {"mcpServers": {}}
    config_file = tmp_path / "claude_desktop_config.json"
    config_file.write_text(json.dumps(config))
    return config_file


@pytest.fixture
def server_file(tmp_path):
    """Create a server file."""
    server_file = tmp_path / "server.py"
    server_file.write_text(
        """from fastmcp import FastMCP
mcp = FastMCP("test")
"""
    )
    return server_file


@pytest.fixture
def mock_env_file(tmp_path):
    """Create a mock .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ=123")
    return env_file


def test_parse_env_var():
    """Test parsing environment variables."""
    assert _parse_env_var("FOO=bar") == ("FOO", "bar")
    assert _parse_env_var("FOO=") == ("FOO", "")
    assert _parse_env_var("FOO=bar baz") == ("FOO", "bar baz")
    assert _parse_env_var("FOO = bar ") == ("FOO", "bar")

    with pytest.raises(SystemExit):
        _parse_env_var("invalid")


@pytest.mark.parametrize(
    "args,expected_env",
    [
        # Basic env var
        (
            ["--env-var", "FOO=bar"],
            {"FOO": "bar"},
        ),
        # Multiple env vars
        (
            ["--env-var", "FOO=bar", "--env-var", "BAZ=123"],
            {"FOO": "bar", "BAZ": "123"},
        ),
        # Env var with spaces
        (
            ["--env-var", "FOO=bar baz"],
            {"FOO": "bar baz"},
        ),
    ],
)
def test_install_with_env_vars(mock_config, server_file, args, expected_env):
    """Test installing with environment variables."""
    runner = CliRunner()

    with patch("fastmcp.cli.claude.get_claude_config_path") as mock_config_path:
        mock_config_path.return_value = mock_config.parent

        result = runner.invoke(
            app,
            ["install", str(server_file)] + args,
        )

        assert result.exit_code == 0

        # Read the config file and check env vars
        config = json.loads(mock_config.read_text())
        assert "mcpServers" in config
        assert len(config["mcpServers"]) == 1
        server = next(iter(config["mcpServers"].values()))
        assert server["env"] == expected_env


def test_parse_file_path_windows_drive():
    """Test parsing a Windows file path with a drive letter."""
    file_spec = r"C:\path\to\file.txt"
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
    ):
        file_path, server_object = _parse_file_path(file_spec)
        assert file_path == Path(r"C:\path\to\file.txt").resolve()
        assert server_object is None


def test_parse_file_path_with_object():
    """Test parsing a file path with an object specification."""
    file_spec = "/path/to/file.txt:object"
    with patch("sys.exit") as mock_exit:
        _parse_file_path(file_spec)

        # Check that sys.exit was called twice with code 1
        assert mock_exit.call_count == 2
        mock_exit.assert_has_calls([call(1), call(1)])


def test_parse_file_path_windows_with_object():
    """Test parsing a Windows file path with an object specification."""
    file_spec = r"C:\path\to\file.txt:object"
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
    ):
        file_path, server_object = _parse_file_path(file_spec)
        assert file_path == Path(r"C:\path\to\file.txt").resolve()
        assert server_object == "object"


def test_install_with_env_file(mock_config, server_file, mock_env_file):
    """Test installing with environment variables from a file."""
    runner = CliRunner()

    with patch("fastmcp.cli.claude.get_claude_config_path") as mock_config_path:
        mock_config_path.return_value = mock_config.parent

        result = runner.invoke(
            app,
            ["install", str(server_file), "--env-file", str(mock_env_file)],
        )

        assert result.exit_code == 0

        # Read the config file and check env vars
        config = json.loads(mock_config.read_text())
        assert "mcpServers" in config
        assert len(config["mcpServers"]) == 1
        server = next(iter(config["mcpServers"].values()))
        assert server["env"] == {"FOO": "bar", "BAZ": "123"}


def test_install_preserves_existing_env_vars(mock_config, server_file):
    """Test that installing preserves existing environment variables."""
    # Set up initial config with env vars
    config = {
        "mcpServers": {
            "test": {
                "command": "uv",
                "args": [
                    "run",
                    "--with",
                    "fastmcp",
                    "fastmcp",
                    "run",
                    str(server_file),
                ],
                "env": {"FOO": "bar", "BAZ": "123"},
            }
        }
    }
    mock_config.write_text(json.dumps(config))

    runner = CliRunner()

    with patch("fastmcp.cli.claude.get_claude_config_path") as mock_config_path:
        mock_config_path.return_value = mock_config.parent

        # Install with a new env var
        result = runner.invoke(
            app,
            ["install", str(server_file), "--env-var", "NEW=value"],
        )

        assert result.exit_code == 0

        # Read the config file and check env vars are preserved
        config = json.loads(mock_config.read_text())
        server = next(iter(config["mcpServers"].values()))
        assert server["env"] == {"FOO": "bar", "BAZ": "123", "NEW": "value"}


def test_install_updates_existing_env_vars(mock_config, server_file):
    """Test that installing updates existing environment variables."""
    # Set up initial config with env vars
    config = {
        "mcpServers": {
            "test": {
                "command": "uv",
                "args": [
                    "run",
                    "--with",
                    "fastmcp",
                    "fastmcp",
                    "run",
                    str(server_file),
                ],
                "env": {"FOO": "bar", "BAZ": "123"},
            }
        }
    }
    mock_config.write_text(json.dumps(config))

    runner = CliRunner()

    with patch("fastmcp.cli.claude.get_claude_config_path") as mock_config_path:
        mock_config_path.return_value = mock_config.parent

        # Update an existing env var
        result = runner.invoke(
            app,
            ["install", str(server_file), "--env-var", "FOO=newvalue"],
        )

        assert result.exit_code == 0

        # Read the config file and check env var was updated
        config = json.loads(mock_config.read_text())
        server = next(iter(config["mcpServers"].values()))
        assert server["env"] == {"FOO": "newvalue", "BAZ": "123"}


def test_server_dependencies(mock_config, server_file):
    """Test that server dependencies are correctly handled."""
    # Create a server file with dependencies
    server_file = server_file.parent / "server_with_deps.py"
    server_file.write_text(
        """from fastmcp import FastMCP
mcp = FastMCP("test", dependencies=["pandas", "numpy"])
"""
    )

    runner = CliRunner()

    with patch("fastmcp.cli.claude.get_claude_config_path") as mock_config_path:
        mock_config_path.return_value = mock_config.parent

        result = runner.invoke(app, ["install", str(server_file)])

        assert result.exit_code == 0

        # Read the config file and check dependencies were added as --with args
        config = json.loads(mock_config.read_text())
        server = next(iter(config["mcpServers"].values()))
        assert "--with" in server["args"]
        assert "pandas" in server["args"]
        assert "numpy" in server["args"]


def test_server_dependencies_empty(mock_config, server_file):
    """Test that server with no dependencies works correctly."""
    runner = CliRunner()

    with patch("fastmcp.cli.claude.get_claude_config_path") as mock_config_path:
        mock_config_path.return_value = mock_config.parent

        result = runner.invoke(app, ["install", str(server_file)])

        assert result.exit_code == 0

        # Read the config file and check only fastmcp is in --with args
        config = json.loads(mock_config.read_text())
        server = next(iter(config["mcpServers"].values()))
        assert server["args"].count("--with") == 1
        assert "fastmcp" in server["args"]


def test_dev_with_dependencies(mock_config, server_file):
    """Test that dev command handles dependencies correctly."""
    # Create a server file with dependencies
    server_file = server_file.parent / "server_with_deps.py"
    server_file.write_text(
        """from fastmcp import FastMCP
mcp = FastMCP("test", dependencies=["pandas", "numpy"])
"""
    )

    runner = CliRunner()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0  # Set successful return code
        result = runner.invoke(app, ["dev", str(server_file)])
        assert result.exit_code == 0

        # Check that dependencies were passed to subprocess.run
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "npx" in args
        assert "@modelcontextprotocol/inspector" in args
        assert "uv" in args
        assert "run" in args
        assert "--with" in args
        assert "pandas" in args
        assert "numpy" in args
        assert "fastmcp" in args


def test_run_with_dependencies(mock_config, server_file):
    """Test that run command does not handle dependencies."""
    # Create a server file with dependencies
    server_file = server_file.parent / "server_with_deps.py"
    server_file.write_text(
        """from fastmcp import FastMCP
mcp = FastMCP("test", dependencies=["pandas", "numpy"])

if __name__ == "__main__":
    mcp.run()
"""
    )

    runner = CliRunner()

    with patch("subprocess.run") as mock_run:
        result = runner.invoke(app, ["run", str(server_file)])
        assert result.exit_code == 0

        # Run command should not call subprocess.run
        mock_run.assert_not_called()
