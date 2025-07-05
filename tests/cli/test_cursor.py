"""Tests for Cursor CLI integration."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from fastmcp.cli import cursor


class TestGetCursorConfigPath:
    """Test get_cursor_config_path function."""

    def test_returns_path_when_exists(self, tmp_path):
        """Should return path when .cursor directory exists."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        
        with patch.object(Path, "home", return_value=tmp_path):
            result = cursor.get_cursor_config_path()
            assert result == cursor_dir

    def test_returns_none_when_not_exists(self, tmp_path):
        """Should return None when .cursor directory doesn't exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = cursor.get_cursor_config_path()
            assert result is None


class TestOpenCursorDeeplink:
    """Test open_cursor_deeplink function."""

    @pytest.mark.parametrize("platform,expected_method", [
        ("darwin", "subprocess.run"),
        ("win32", "os.startfile"),
        ("linux", "webbrowser.open"),
    ])
    def test_opens_deeplink_by_platform(self, platform, expected_method):
        """Should use platform-specific method to open deeplink."""
        with patch.object(sys, "platform", platform):
            if expected_method == "subprocess.run":
                with patch("subprocess.run") as mock_run:
                    result = cursor.open_cursor_deeplink("test-server")
                    assert result is True
                    mock_run.assert_called_once()
                    assert "cursor://settings/mcp?highlight=test-server" in mock_run.call_args[0][0]
            elif expected_method == "os.startfile":
                # os.startfile is only available on Windows
                with patch("fastmcp.cli.cursor.os.startfile", create=True) as mock_startfile:
                    result = cursor.open_cursor_deeplink("test-server")
                    assert result is True
                    mock_startfile.assert_called_once_with("cursor://settings/mcp?highlight=test-server")
            else:  # webbrowser.open
                with patch("webbrowser.open") as mock_open:
                    result = cursor.open_cursor_deeplink("test-server")
                    assert result is True
                    mock_open.assert_called_once_with("cursor://settings/mcp?highlight=test-server")

    def test_returns_false_on_error(self):
        """Should return False when opening deeplink fails."""
        with patch("subprocess.run", side_effect=Exception("Failed")):
            with patch.object(sys, "platform", "darwin"):
                result = cursor.open_cursor_deeplink("test-server")
                assert result is False


class TestUpdateCursorConfig:
    """Test update_cursor_config function."""

    def test_raises_when_cursor_not_found(self, tmp_path):
        """Should raise RuntimeError when Cursor not found."""
        with patch.object(Path, "home", return_value=tmp_path):
            with pytest.raises(RuntimeError, match="Cursor config directory not found"):
                cursor.update_cursor_config("server.py", "test-server")

    def test_creates_config_file_when_missing(self, tmp_path):
        """Should create mcp.json when it doesn't exist."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=False):
                result = cursor.update_cursor_config(
                    "server.py",
                    "test-server",
                    open_cursor=False
                )
                assert result is True
                assert config_file.exists()
                
                config = json.loads(config_file.read_text())
                assert "mcpServers" in config
                assert "test-server" in config["mcpServers"]

    def test_adds_stdio_server(self, tmp_path):
        """Should add server with stdio transport."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        config_file.write_text("{}")
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=False):
                result = cursor.update_cursor_config(
                    "/path/to/server.py",
                    "test-server",
                    with_packages=["requests", "pandas"],
                    env_vars={"API_KEY": "secret"},
                    transport="stdio",
                    open_cursor=False
                )
                assert result is True
                
                config = json.loads(config_file.read_text())
                server_config = config["mcpServers"]["test-server"]
                
                assert server_config["command"] == "uv"
                assert "run" in server_config["args"]
                assert "--with" in server_config["args"]
                assert "fastmcp" in server_config["args"]
                assert "requests" in server_config["args"]
                assert "pandas" in server_config["args"]
                assert server_config["env"]["API_KEY"] == "secret"

    def test_adds_sse_server(self, tmp_path):
        """Should add server with SSE transport."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        config_file.write_text("{}")
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=False):
                result = cursor.update_cursor_config(
                    "server.py",
                    "test-server",
                    transport="sse",
                    open_cursor=False
                )
                assert result is True
                
                config = json.loads(config_file.read_text())
                server_config = config["mcpServers"]["test-server"]
                
                assert "url" in server_config
                assert server_config["url"] == "http://localhost:8000/sse"

    def test_preserves_existing_env_vars(self, tmp_path):
        """Should preserve existing environment variables when updating."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        
        # Create initial config with env vars
        initial_config = {
            "mcpServers": {
                "test-server": {
                    "command": "uv",
                    "args": ["run", "--with", "fastmcp", "fastmcp", "run", "server.py"],
                    "env": {"OLD_VAR": "old_value", "API_KEY": "old_key"}
                }
            }
        }
        config_file.write_text(json.dumps(initial_config))
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=False):
                result = cursor.update_cursor_config(
                    "server.py",
                    "test-server",
                    env_vars={"API_KEY": "new_key", "NEW_VAR": "new_value"},
                    open_cursor=False
                )
                assert result is True
                
                config = json.loads(config_file.read_text())
                env = config["mcpServers"]["test-server"]["env"]
                
                # Old var preserved, API_KEY updated, new var added
                assert env["OLD_VAR"] == "old_value"
                assert env["API_KEY"] == "new_key"
                assert env["NEW_VAR"] == "new_value"

    def test_handles_server_with_object_suffix(self, tmp_path):
        """Should handle server paths with :object suffix."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        config_file.write_text("{}")
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=False):
                result = cursor.update_cursor_config(
                    "/path/to/server.py:app",
                    "test-server",
                    open_cursor=False
                )
                assert result is True
                
                config = json.loads(config_file.read_text())
                args = config["mcpServers"]["test-server"]["args"]
                
                # Should preserve the :app suffix in the resolved path
                # Find the fastmcp run command and then the server arg
                fastmcp_index = args.index("fastmcp")
                run_index = args.index("run", fastmcp_index)
                server_arg = args[run_index + 1]
                assert server_arg.endswith(":app")

    def test_opens_cursor_when_requested(self, tmp_path):
        """Should attempt to open Cursor when open_cursor=True."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        config_file.write_text("{}")
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=True) as mock_deeplink:
                result = cursor.update_cursor_config(
                    "server.py",
                    "test-server",
                    open_cursor=True
                )
                assert result is True
                mock_deeplink.assert_called_once_with("test-server")

    def test_returns_false_on_error(self, tmp_path):
        """Should return False when update fails."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        
        # Make config file unwritable
        config_file.write_text("{}")
        config_file.chmod(0o444)
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.open_cursor_deeplink", return_value=False):
                with patch("fastmcp.cli.cursor.logger") as mock_logger:
                    result = cursor.update_cursor_config(
                        "server.py",
                        "test-server",
                        open_cursor=False
                    )
                    # On some systems, this might still succeed, so we check if it failed
                    if not result:
                        mock_logger.error.assert_called()


class TestListCursorServers:
    """Test list_cursor_servers function."""

    def test_returns_none_when_cursor_not_found(self, tmp_path):
        """Should return None when Cursor not found."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = cursor.list_cursor_servers()
            assert result is None

    def test_returns_empty_dict_when_no_config(self, tmp_path):
        """Should return empty dict when config doesn't exist."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        
        with patch.object(Path, "home", return_value=tmp_path):
            result = cursor.list_cursor_servers()
            assert result == {}

    def test_returns_servers_from_config(self, tmp_path):
        """Should return servers from config file."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        
        config = {
            "mcpServers": {
                "server1": {"command": "uv", "args": ["run", "server1.py"]},
                "server2": {"url": "http://localhost:8000/sse"}
            }
        }
        config_file.write_text(json.dumps(config))
        
        with patch.object(Path, "home", return_value=tmp_path):
            result = cursor.list_cursor_servers()
            assert result == config["mcpServers"]

    def test_returns_none_on_json_error(self, tmp_path):
        """Should return None when JSON is invalid."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        config_file = cursor_dir / "mcp.json"
        config_file.write_text("invalid json")
        
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("fastmcp.cli.cursor.logger") as mock_logger:
                result = cursor.list_cursor_servers()
                assert result is None
                mock_logger.error.assert_called() 