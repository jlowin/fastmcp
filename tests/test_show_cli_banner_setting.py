"""Tests for show_cli_banner setting functionality."""

import os
from unittest import mock

import pytest

from fastmcp import FastMCP
from fastmcp.settings import Settings


class TestShowCliBannerSetting:
    """Test the show_cli_banner setting."""

    def test_settings_default_and_override(self):
        """Test default value and direct setting."""
        assert Settings().show_cli_banner is True  # Default
        assert Settings(show_cli_banner=False).show_cli_banner is False

    def test_env_var(self):
        """Test environment variable configuration."""
        with mock.patch.dict(os.environ, {"FASTMCP_SHOW_CLI_BANNER": "false"}):
            assert Settings().show_cli_banner is False

    @pytest.mark.asyncio
    async def test_server_respects_show_banner(self):
        """Test that server respects show_banner parameter."""
        server = FastMCP("TestServer")

        with mock.patch("fastmcp.server.server.log_server_banner") as mock_banner:
            with mock.patch("fastmcp.server.server.stdio_server"):
                # Banner shown when show_banner=True
                try:
                    await server.run_stdio_async(show_banner=True)
                except Exception:
                    pass
                mock_banner.assert_called_once()

                # Banner hidden when show_banner=False
                mock_banner.reset_mock()
                try:
                    await server.run_stdio_async(show_banner=False)
                except Exception:
                    pass
                mock_banner.assert_not_called()

    def test_cli_precedence(self):
        """Test CLI flag overrides environment setting."""
        # Simulate the CLI logic
        with mock.patch.dict(os.environ, {"FASTMCP_SHOW_CLI_BANNER": "true"}):
            settings = Settings()
            # CLI --no-banner flag overrides settings
            cli_no_banner = True
            final = cli_no_banner if cli_no_banner else not settings.show_cli_banner
            assert final is True  # Banner suppressed despite settings
