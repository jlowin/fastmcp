"""Tests for debug and starlette_debug settings."""

import logging

import pytest

from fastmcp import settings as global_settings
from fastmcp.settings import Settings
from fastmcp.utilities.logging import get_logger


class TestDebugSettings:
    """Test debug and starlette_debug settings behavior."""

    def test_debug_sets_log_level(self):
        """Test that enabling debug sets log_level to DEBUG."""
        settings = Settings(debug=True, log_enabled=False)
        assert settings.log_level == "DEBUG"

    def test_debug_false_preserves_log_level(self):
        """Test that debug=False doesn't change log_level."""
        settings = Settings(debug=False, log_level="INFO", log_enabled=False)
        assert settings.log_level == "INFO"

    def test_debug_with_explicit_log_level(self):
        """Test that debug=True overrides explicit log_level."""
        # When debug is enabled, it forces log_level to DEBUG
        settings = Settings(debug=True, log_level="WARNING", log_enabled=False)
        assert settings.log_level == "DEBUG"

    def test_starlette_debug_independent(self, monkeypatch):
        """Test that starlette_debug works independently."""
        # Clear any env vars that might affect the test
        monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
        settings = Settings(starlette_debug=True, log_enabled=False)
        assert settings.starlette_debug is True
        # log_level should not be affected (defaults to INFO)
        assert settings.log_level == "INFO"

    def test_both_debug_and_starlette_debug(self):
        """Test that both settings can be enabled together."""
        settings = Settings(debug=True, starlette_debug=True, log_enabled=False)
        assert settings.debug is True
        assert settings.starlette_debug is True
        assert settings.log_level == "DEBUG"

    def test_debug_reconfigures_logging(self):
        """Test that enabling debug reconfigures logging."""
        # Create a settings instance with debug enabled
        settings = Settings(debug=True, log_enabled=True)

        # Verify logging was reconfigured
        logger = get_logger("test")
        assert logger.getEffectiveLevel() == logging.DEBUG

    def test_debug_respects_log_enabled(self):
        """Test that debug respects log_enabled setting."""
        # When log_enabled is False, logging should not be reconfigured
        settings = Settings(debug=True, log_enabled=False)
        assert settings.log_level == "DEBUG"
        # Logger should not be reconfigured, but we can't easily test this
        # without side effects

    def test_starlette_debug_default_false(self):
        """Test that starlette_debug defaults to False."""
        settings = Settings(log_enabled=False)
        assert settings.starlette_debug is False

    def test_debug_default_false(self):
        """Test that debug defaults to False."""
        settings = Settings(log_enabled=False)
        assert settings.debug is False

    def test_env_var_debug(self, monkeypatch):
        """Test that FASTMCP_DEBUG environment variable works."""
        monkeypatch.setenv("FASTMCP_DEBUG", "true")
        settings = Settings(log_enabled=False)
        assert settings.debug is True
        assert settings.log_level == "DEBUG"

    def test_env_var_starlette_debug(self, monkeypatch):
        """Test that FASTMCP_STARLETTE_DEBUG environment variable works."""
        # Clear any env vars that might affect the test
        monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
        monkeypatch.setenv("FASTMCP_STARLETTE_DEBUG", "true")
        settings = Settings(log_enabled=False)
        assert settings.starlette_debug is True
        # log_level should not be affected (defaults to INFO)
        assert settings.log_level == "INFO"
