"""Tests for client logging bug fix (issue #1394)."""

from unittest.mock import MagicMock, patch

import pytest
from mcp.types import LoggingMessageNotificationParams

from fastmcp.client.logging import default_log_handler


@pytest.mark.asyncio
async def test_default_log_handler_routes_to_correct_levels():
    """Test that default_log_handler routes server logs to appropriate Python log levels."""

    with patch("fastmcp.client.logging.logger") as mock_logger:
        # Set up mock methods
        mock_logger.debug = MagicMock()
        mock_logger.info = MagicMock()
        mock_logger.warning = MagicMock()
        mock_logger.error = MagicMock()
        mock_logger.critical = MagicMock()

        # Test each log level
        test_cases = [
            ("debug", mock_logger.debug, "Debug message"),
            ("info", mock_logger.info, "Info message"),
            ("notice", mock_logger.info, "Notice message"),  # notice -> info
            ("warning", mock_logger.warning, "Warning message"),
            ("error", mock_logger.error, "Error message"),
            ("critical", mock_logger.critical, "Critical message"),
            ("alert", mock_logger.critical, "Alert message"),  # alert -> critical
            (
                "emergency",
                mock_logger.critical,
                "Emergency message",
            ),  # emergency -> critical
        ]

        for level, expected_method, msg in test_cases:
            # Reset mocks
            mock_logger.reset_mock()

            # Create log message
            log_msg = LoggingMessageNotificationParams(
                level=level,  # type: ignore[arg-type]
                logger="test.logger",
                data={"msg": msg, "extra": {"test_key": "test_value"}},
            )

            # Call handler
            await default_log_handler(log_msg)

            # Verify correct method was called
            expected_method.assert_called_once_with(
                f"Server log: [test.logger] {msg}", extra={"test_key": "test_value"}
            )


@pytest.mark.asyncio
async def test_default_log_handler_without_logger_name():
    """Test that default_log_handler works when logger name is None."""

    with patch("fastmcp.client.logging.logger") as mock_logger:
        mock_logger.info = MagicMock()

        log_msg = LoggingMessageNotificationParams(
            level="info",
            logger=None,
            data={"msg": "Message without logger", "extra": {}},
        )

        await default_log_handler(log_msg)

        mock_logger.info.assert_called_once_with(
            "Server log: Message without logger", extra={}
        )


@pytest.mark.asyncio
async def test_default_log_handler_with_missing_msg():
    """Test that default_log_handler handles missing 'msg' gracefully."""

    with patch("fastmcp.client.logging.logger") as mock_logger:
        mock_logger.info = MagicMock()

        log_msg = LoggingMessageNotificationParams(
            level="info",
            logger="test.logger",
            data={"extra": {"key": "value"}},  # Missing 'msg' key
        )

        await default_log_handler(log_msg)

        # Should use str(message) as fallback
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "Server log:" in call_args[0][0]
        assert call_args[1]["extra"] == {"key": "value"}
