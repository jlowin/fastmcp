"""Logging utilities for FastMCP."""

import contextlib
import logging
from typing import Any, Literal, cast

from rich.console import Console
from rich.logging import RichHandler
from typing_extensions import override

import fastmcp


def get_logger(name: str) -> logging.Logger:
    """Get a logger nested under FastMCP namespace.

    Args:
        name: the name of the logger, which will be prefixed with 'FastMCP.'

    Returns:
        a configured logger instance
    """
    if name.startswith("fastmcp."):
        return logging.getLogger(name=name)

    return logging.getLogger(name=f"fastmcp.{name}")


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | int = "INFO",
    logger: logging.Logger | None = None,
    enable_rich_tracebacks: bool | None = None,
    **rich_kwargs: Any,
) -> None:
    """
    Configure logging for FastMCP.

    Args:
        logger: the logger to configure
        level: the log level to use
        rich_kwargs: the parameters to use for creating RichHandler
    """
    # Check if logging is disabled in settings
    if not fastmcp.settings.log_enabled:
        return

    # Use settings default if not specified
    if enable_rich_tracebacks is None:
        enable_rich_tracebacks = fastmcp.settings.enable_rich_tracebacks

    if logger is None:
        logger = logging.getLogger("fastmcp")

    formatter = logging.Formatter("%(message)s")

    # Don't propagate to the root logger
    logger.propagate = False
    logger.setLevel(level)

    # Configure the handler for normal logs
    handler = RichHandler(
        console=Console(stderr=True),
        **rich_kwargs,
    )
    handler.setFormatter(formatter)

    # filter to exclude tracebacks
    handler.addFilter(lambda record: record.exc_info is None)

    # Configure the handler for tracebacks, for tracebacks we use a compressed format:
    # no path or level name to maximize width available for the traceback
    # suppress framework frames and limit the number of frames to 3

    import mcp
    import pydantic

    traceback_handler = RichHandler(
        console=Console(stderr=True),
        show_path=False,
        show_level=False,
        rich_tracebacks=enable_rich_tracebacks,
        tracebacks_max_frames=3,
        tracebacks_suppress=[fastmcp, mcp, pydantic],
        **rich_kwargs,
    )
    traceback_handler.setFormatter(formatter)

    traceback_handler.addFilter(lambda record: record.exc_info is not None)

    # Remove any existing handlers to avoid duplicates on reconfiguration
    for hdlr in logger.handlers[:]:
        logger.removeHandler(hdlr)

    logger.addHandler(handler)
    logger.addHandler(traceback_handler)


@contextlib.contextmanager
def temporary_log_level(
    level: str | None,
    logger: logging.Logger | None = None,
    enable_rich_tracebacks: bool | None = None,
    **rich_kwargs: Any,
):
    """Context manager to temporarily set log level and restore it afterwards.

    Args:
        level: The temporary log level to set (e.g., "DEBUG", "INFO")
        logger: Optional logger to configure (defaults to FastMCP logger)
        enable_rich_tracebacks: Whether to enable rich tracebacks
        **rich_kwargs: Additional parameters for RichHandler

    Usage:
        with temporary_log_level("DEBUG"):
            # Code that runs with DEBUG logging
            pass
        # Original log level is restored here
    """
    if level:
        # Get the original log level from settings
        original_level = fastmcp.settings.log_level

        # Configure with new level
        # Cast to proper type for type checker
        log_level_literal = cast(
            Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            level.upper(),
        )
        configure_logging(
            level=log_level_literal,
            logger=logger,
            enable_rich_tracebacks=enable_rich_tracebacks,
            **rich_kwargs,
        )
        try:
            yield
        finally:
            # Restore original configuration using configure_logging
            # This will respect the log_enabled setting
            configure_logging(
                level=original_level,
                logger=logger,
                enable_rich_tracebacks=enable_rich_tracebacks,
                **rich_kwargs,
            )
    else:
        yield


class ClampedLogFilter(logging.Filter):
    def __init__(
        self, max_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    ):
        self.max_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
            max_level
        )

        self.max_level_no: int

        if max_level == "DEBUG":
            self.max_level_no = logging.DEBUG
        elif max_level == "INFO":
            self.max_level_no = logging.INFO
        elif max_level == "WARNING":
            self.max_level_no = logging.WARNING
        elif max_level == "ERROR":
            self.max_level_no = logging.ERROR
        elif max_level == "CRITICAL":
            self.max_level_no = logging.CRITICAL

        super().__init__()

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= self.max_level_no:
            record.levelno = self.max_level_no
            record.levelname = self.max_level
            return True
        return True


def clamp_logger(
    logger: logging.Logger,
    max_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
) -> None:
    """Clamp the logger to a maximum level -- anything equal or greater than the max level will be set to the max level."""
    unclamp_logger(logger=logger)

    logger.addFilter(filter=ClampedLogFilter(max_level=max_level))


def unclamp_logger(logger: logging.Logger) -> None:
    """Remove all clamped log filters from the logger."""
    for filter in logger.filters[:]:
        if isinstance(filter, ClampedLogFilter):
            logger.removeFilter(filter)
