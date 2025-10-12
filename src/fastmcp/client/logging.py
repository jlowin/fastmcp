from collections.abc import Awaitable, Callable
from logging import Logger
from typing import TypeAlias

from mcp.client.session import LoggingFnT
from mcp.types import LoggingMessageNotificationParams

from fastmcp.utilities.logging import get_logger

logger: Logger = get_logger(__name__)
from_server_logger: Logger = logger.getChild(suffix="from_server")

LogMessage: TypeAlias = LoggingMessageNotificationParams
LogHandler: TypeAlias = Callable[[LogMessage], Awaitable[None]]


async def default_log_handler(message: LogMessage) -> None:
    """Default handler that properly routes server log messages to appropriate log levels."""
    msg = message.data.get("msg", str(message))
    extra = message.data.get("extra", {})

    # Map MCP log levels to Python logging levels
    level_map = {
        "debug": from_server_logger.debug,
        "info": from_server_logger.info,
        "notice": from_server_logger.info,  # Python doesn't have 'notice', map to info
        "warning": from_server_logger.warning,
        "error": from_server_logger.error,
        "critical": from_server_logger.critical,
        "alert": from_server_logger.critical,  # Map alert to critical
        "emergency": from_server_logger.critical,  # Map emergency to critical
    }

    # Get the appropriate logging function based on the message level
    log_fn = level_map.get(message.level.lower(), logger.info)

    # Include logger name if available
    msg_prefix: str = (
        f"[From Server:{message.logger}]" if message.logger else "[From Server]"
    )

    # Log with appropriate level and extra data
    log_fn(msg=f"{msg_prefix} {msg}", extra=extra)


def create_log_callback(handler: LogHandler | None = None) -> LoggingFnT:
    if handler is None:
        handler = default_log_handler

    async def log_callback(params: LoggingMessageNotificationParams) -> None:
        await handler(params)

    return log_callback
