from __future__ import annotations

import asyncio
import logging
import socket
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# Use SelectorEventLoop on Windows to avoid ProactorEventLoop crashes
# See: https://github.com/python/cpython/issues/116773
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def isolate_settings_home(tmp_path: Path) -> Generator[None, None, None]:
    # Import here to avoid import errors if fastmcp isn't installed
    from fastmcp.utilities.tests import temporary_settings

    test_home = tmp_path / "fastmcp-test-home"
    test_home.mkdir(exist_ok=True)

    with temporary_settings(home=test_home):
        yield


@pytest.fixture(autouse=True)
def enable_fastmcp_logger_propagation(
    caplog: pytest.LogCaptureFixture,
) -> Generator[None, None, None]:
    root_logger = logging.getLogger("fastmcp")
    original_propagate = root_logger.propagate
    root_logger.propagate = True
    yield
    root_logger.propagate = original_propagate


@pytest.fixture
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port
