"""Tests for the fastmcp project prepare command."""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastmcp.utilities.fastmcp_config import Environment, FastMCPConfig
from fastmcp.utilities.fastmcp_config.v1.sources.filesystem import FileSystemSource


class TestFastMCPConfigPrepare:
    """Test the FastMCPConfig.prepare() method."""

    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_source",
        new_callable=AsyncMock,
    )
    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_environment",
        new_callable=AsyncMock,
    )
    async def test_prepare_calls_both_methods(self, mock_env, mock_src):
        """Test that prepare() calls both prepare_environment and prepare_source."""
        config = FastMCPConfig(
            source=FileSystemSource(path="server.py"),
            environment=Environment(python="3.10"),
        )

        await config.prepare()

        mock_env.assert_called_once()
        mock_src.assert_called_once()

    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_source",
        new_callable=AsyncMock,
    )
    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_environment",
        new_callable=AsyncMock,
    )
    async def test_prepare_skip_env(self, mock_env, mock_src):
        """Test that prepare() skips environment when skip_env=True."""
        config = FastMCPConfig(
            source=FileSystemSource(path="server.py"),
            environment=Environment(python="3.10"),
        )

        await config.prepare(skip_env=True, skip_source=False)

        mock_env.assert_not_called()
        mock_src.assert_called_once()

    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_source",
        new_callable=AsyncMock,
    )
    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_environment",
        new_callable=AsyncMock,
    )
    async def test_prepare_skip_source(self, mock_env, mock_src):
        """Test that prepare() skips source when skip_source=True."""
        config = FastMCPConfig(
            source=FileSystemSource(path="server.py"),
            environment=Environment(python="3.10"),
        )

        await config.prepare(skip_env=False, skip_source=True)

        mock_env.assert_called_once()
        mock_src.assert_not_called()

    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_source",
        new_callable=AsyncMock,
    )
    @patch(
        "fastmcp.utilities.fastmcp_config.v1.fastmcp_config.FastMCPConfig.prepare_environment",
        new_callable=AsyncMock,
    )
    async def test_prepare_skip_both(self, mock_env, mock_src):
        """Test that prepare() skips both when both flags are True."""
        config = FastMCPConfig(
            source=FileSystemSource(path="server.py"),
            environment=Environment(python="3.10"),
        )

        await config.prepare(skip_env=True, skip_source=True)

        mock_env.assert_not_called()
        mock_src.assert_not_called()


class TestEnvironmentPrepare:
    """Test the Environment.prepare() method."""

    @patch("shutil.which")
    async def test_prepare_no_uv_installed(self, mock_which):
        """Test that prepare() raises error when uv is not installed."""
        mock_which.return_value = None

        env = Environment(python="3.10")

        with pytest.raises(RuntimeError, match="uv is not installed"):
            await env.prepare()

    @patch("subprocess.run")
    @patch("shutil.which")
    async def test_prepare_no_settings(self, mock_which, mock_run):
        """Test that prepare() does nothing when no settings are configured."""
        mock_which.return_value = "/usr/bin/uv"

        env = Environment()  # No settings

        await env.prepare()

        # Should not run any commands
        mock_run.assert_not_called()

    @patch("subprocess.run")
    @patch("shutil.which")
    async def test_prepare_with_python(self, mock_which, mock_run):
        """Test that prepare() runs uv with python version."""
        mock_which.return_value = "/usr/bin/uv"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Environment cached", stderr=""
        )

        env = Environment(python="3.10")

        await env.prepare()

        # Should run uv with python version
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "uv"
        assert "--python" in args
        assert "3.10" in args
        # Should run a Python command to cache the environment
        assert "python" in args
        assert "-c" in args

    @patch("subprocess.run")
    @patch("shutil.which")
    async def test_prepare_with_dependencies(self, mock_which, mock_run):
        """Test that prepare() includes dependencies."""
        mock_which.return_value = "/usr/bin/uv"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        env = Environment(dependencies=["numpy", "pandas"])

        await env.prepare()

        # Should include dependencies in uv command
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "--with" in args
        assert "numpy" in args
        assert "pandas" in args

    @patch("subprocess.run")
    @patch("shutil.which")
    async def test_prepare_command_fails(self, mock_which, mock_run):
        """Test that prepare() raises error when uv command fails."""
        mock_which.return_value = "/usr/bin/uv"
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["uv"], stderr="Package not found"
        )

        env = Environment(python="3.10")

        with pytest.raises(RuntimeError, match="Environment preparation failed"):
            await env.prepare()


class TestProjectPrepareCommand:
    """Test the CLI project prepare command."""

    @patch("fastmcp.utilities.fastmcp_config.FastMCPConfig.from_file")
    @patch("fastmcp.utilities.fastmcp_config.FastMCPConfig.find_config")
    async def test_project_prepare_auto_detect(self, mock_find, mock_from_file):
        """Test project prepare with auto-detected config."""
        from fastmcp.cli.cli import prepare

        # Setup mocks
        mock_find.return_value = Path("fastmcp.json")
        mock_config = AsyncMock()
        mock_from_file.return_value = mock_config

        # Run command with no args (should auto-detect)
        with patch("sys.exit"):
            with patch("fastmcp.cli.cli.console.print") as mock_print:
                await prepare(config_path=None)

        # Should find and load config
        mock_find.assert_called_once()
        mock_from_file.assert_called_once_with(Path("fastmcp.json"))

        # Should call prepare with no skips
        mock_config.prepare.assert_called_once_with(skip_env=False, skip_source=False)

        # Should print success message
        mock_print.assert_called()
        success_call = mock_print.call_args_list[-1][0][0]
        assert "Project prepared successfully" in success_call

    @patch("pathlib.Path.exists")
    @patch("fastmcp.utilities.fastmcp_config.FastMCPConfig.from_file")
    async def test_project_prepare_explicit_path(self, mock_from_file, mock_exists):
        """Test project prepare with explicit config path."""
        from fastmcp.cli.cli import prepare

        # Setup mocks
        mock_exists.return_value = True
        mock_config = AsyncMock()
        mock_from_file.return_value = mock_config

        # Run command with explicit path
        with patch("fastmcp.cli.cli.console.print"):
            await prepare(config_path="myconfig.json")

        # Should load specified config
        mock_from_file.assert_called_once_with(Path("myconfig.json"))

        # Should call prepare
        mock_config.prepare.assert_called_once_with(skip_env=False, skip_source=False)

    @patch("fastmcp.utilities.fastmcp_config.FastMCPConfig.find_config")
    async def test_project_prepare_no_config_found(self, mock_find):
        """Test project prepare when no config is found."""
        from fastmcp.cli.cli import prepare

        # Setup mocks
        mock_find.return_value = None

        # Run command - should exit with error
        with pytest.raises(SystemExit) as exc_info:
            with patch("fastmcp.cli.cli.logger.error") as mock_error:
                await prepare(config_path=None)

        assert exc_info.value.code == 1
        mock_error.assert_called()
        error_msg = mock_error.call_args[0][0]
        assert "no fastmcp.json found" in error_msg

    @patch("pathlib.Path.exists")
    async def test_project_prepare_config_not_exists(self, mock_exists):
        """Test project prepare when specified config doesn't exist."""
        from fastmcp.cli.cli import prepare

        # Setup mocks
        mock_exists.return_value = False

        # Run command - should exit with error
        with pytest.raises(SystemExit) as exc_info:
            with patch("fastmcp.cli.cli.logger.error") as mock_error:
                await prepare(config_path="missing.json")

        assert exc_info.value.code == 1
        mock_error.assert_called()
        error_msg = mock_error.call_args[0][0]
        assert "not found" in error_msg

    @patch("pathlib.Path.exists")
    @patch("fastmcp.utilities.fastmcp_config.FastMCPConfig.from_file")
    async def test_project_prepare_failure(self, mock_from_file, mock_exists):
        """Test project prepare when prepare() fails."""
        from fastmcp.cli.cli import prepare

        # Setup mocks
        mock_exists.return_value = True
        mock_config = AsyncMock()
        mock_config.prepare.side_effect = RuntimeError("Preparation failed")
        mock_from_file.return_value = mock_config

        # Run command - should exit with error
        with pytest.raises(SystemExit) as exc_info:
            with patch("fastmcp.cli.cli.console.print") as mock_print:
                await prepare(config_path="config.json")

        assert exc_info.value.code == 1
        # Should print error message
        error_call = mock_print.call_args_list[-1][0][0]
        assert "Failed to prepare project" in error_call
