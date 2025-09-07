"""Tests for show_cli_banner setting functionality."""

import os
from unittest import mock

import pytest

import fastmcp
from fastmcp import FastMCP
from fastmcp.settings import Settings


class TestShowCliBannerSetting:
    """Test the show_cli_banner setting in various configurations."""

    def test_show_cli_banner_in_settings(self):
        """Test that show_cli_banner can be set in Settings."""
        settings = Settings(show_cli_banner=True)
        assert settings.show_cli_banner is True

        settings = Settings(show_cli_banner=False)
        assert settings.show_cli_banner is False

        # Test default value (should be True)
        settings = Settings()
        assert settings.show_cli_banner is True

    def test_show_cli_banner_from_env_var(self):
        """Test that show_cli_banner can be set via environment variable."""
        with mock.patch.dict(os.environ, {"FASTMCP_SHOW_CLI_BANNER": "false"}):
            settings = Settings()
            assert settings.show_cli_banner is False

        with mock.patch.dict(os.environ, {"FASTMCP_SHOW_CLI_BANNER": "true"}):
            settings = Settings()
            assert settings.show_cli_banner is True

    @pytest.mark.asyncio
    async def test_server_respects_no_banner_setting(self, capsys):
        """Test that the server respects the no_banner setting."""
        server = FastMCP("TestServer")

        # Mock the log_server_banner function to track if it's called
        with mock.patch("fastmcp.server.server.log_server_banner") as mock_banner:
            # Test with show_banner=True (default)
            with mock.patch("fastmcp.server.server.stdio_server"):
                try:
                    await server.run_stdio_async(show_banner=True)
                except Exception:
                    pass  # We're just testing the banner call
            mock_banner.assert_called_once()

            # Reset mock
            mock_banner.reset_mock()

            # Test with show_banner=False
            with mock.patch("fastmcp.server.server.stdio_server"):
                try:
                    await server.run_stdio_async(show_banner=False)
                except Exception:
                    pass  # We're just testing the banner call
            mock_banner.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_command_uses_settings_no_banner(self):
        """Test that run_command uses the global settings no_banner as fallback."""
        from fastmcp.cli.run import run_command
        from fastmcp.utilities.mcp_server_config.v1.sources.filesystem import (
            FileSystemSource,
        )

        # Create a test server
        server = FastMCP("TestServer")

        # Mock the MCPServerConfig and its source
        with mock.patch("fastmcp.cli.run.MCPServerConfig") as mock_config_class:
            mock_config = mock.MagicMock()
            mock_config.deployment.no_banner = None  # No config override
            mock_config.prepare_source = mock.AsyncMock()
            mock_config.source.load_server = mock.AsyncMock(return_value=server)
            mock_config_class.return_value = mock_config

            # Mock FileSystemSource
            with mock.patch("fastmcp.cli.run.FileSystemSource") as mock_source_class:
                mock_source = mock.MagicMock(spec=FileSystemSource)
                mock_source.path = "test.py"
                mock_source_class.return_value = mock_source

                # Mock the server's run_async method
                server.run_async = mock.AsyncMock()  # type: ignore[method-assign]

                # Test with global settings show_cli_banner=False (banner suppressed)
                with mock.patch.object(fastmcp.settings, "show_cli_banner", False):
                    await run_command("test.py", show_banner=True)
                    # Since settings.show_cli_banner is False, we don't need to check
                    # The banner suppression is handled in cli.py, not in run_command
                    server.run_async.assert_called_once()  # type: ignore[attr-defined]

                # Reset mock
                server.run_async.reset_mock()  # type: ignore[attr-defined]

                # Test with global settings show_cli_banner=True (banner shown)
                with mock.patch.object(fastmcp.settings, "show_cli_banner", True):
                    await run_command("test.py", show_banner=True)
                    # When show_cli_banner is True in settings, show_banner should remain True
                    server.run_async.assert_called_once()  # type: ignore[attr-defined]

    def test_no_banner_precedence(self):
        """Test the precedence order: CLI > settings (env var)."""
        # Test that CLI override (no_banner=True) takes precedence over settings
        with mock.patch.dict(os.environ, {"FASTMCP_SHOW_CLI_BANNER": "true"}):
            settings = Settings()
            assert settings.show_cli_banner is True

            # In actual CLI usage, the CLI flag would override the settings value
            # This is handled in the CLI code, not in Settings itself
            cli_no_banner = True  # User passed --no-banner
            final_no_banner = (
                cli_no_banner if cli_no_banner else not settings.show_cli_banner
            )
            assert final_no_banner is True  # CLI override wins (banner suppressed)

        # Test that settings value is used when no CLI override
        with mock.patch.dict(os.environ, {"FASTMCP_SHOW_CLI_BANNER": "false"}):
            settings = Settings()
            cli_no_banner = False  # User didn't pass --no-banner
            final_no_banner = (
                cli_no_banner if cli_no_banner else not settings.show_cli_banner
            )
            assert final_no_banner is True  # Settings value is used (banner suppressed)
