import logging
import socket
import sys
import warnings
from collections.abc import Callable
from typing import Any

import anyio
import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure AnyIO to only use asyncio backend (not trio)."""
    return "asyncio"


@pytest.fixture
async def task_group():
    """Provides a task group for running servers in-process."""
    async with anyio.create_task_group() as tg:
        yield tg
        tg.cancel_scope.cancel()


@pytest.fixture(autouse=True)
def suppress_cancellation_errors(monkeypatch):
    """Suppress expected cancellation errors during server teardown."""

    # Filter out expected cancellation errors from uvicorn/starlette
    class CancelledErrorFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            # Suppress CancelledError-related messages
            if "CancelledError" in msg:
                return False
            if "Traceback" in msg and "lifespan" in msg:
                return False
            # Suppress task group errors during teardown
            if "Task group is not initialized" in msg:
                return False
            if "RuntimeError" in msg and "teardown" in str(record.pathname):
                return False
            return True

    # Suppress warnings about CancelledError
    warnings.filterwarnings(
        "ignore", category=RuntimeWarning, message=".*CancelledError.*"
    )

    # Apply to uvicorn and starlette loggers
    for logger_name in ["uvicorn.error", "uvicorn", "starlette"]:
        logger = logging.getLogger(logger_name)
        filter_obj = CancelledErrorFilter()
        logger.addFilter(filter_obj)

    # Suppress stderr during teardown by capturing and filtering
    original_stderr_write = sys.stderr.write

    def filtered_stderr_write(msg):
        if any(
            pattern in msg
            for pattern in [
                "CancelledError",
                "Task group is not initialized",
                "Exception in ASGI application",
            ]
        ):
            return len(msg)
        return original_stderr_write(msg)

    monkeypatch.setattr(sys.stderr, "write", filtered_stderr_write)

    yield

    # Cleanup filters after test
    for logger_name in ["uvicorn.error", "uvicorn", "starlette"]:
        logger = logging.getLogger(logger_name)
        for filter_obj in logger.filters[:]:
            if isinstance(filter_obj, CancelledErrorFilter):
                logger.removeFilter(filter_obj)


def pytest_collection_modifyitems(items):
    """Automatically mark tests in integration_tests folder with 'integration' marker."""
    for item in items:
        # Check if the test is in the integration_tests folder
        if "integration_tests" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def import_rich_rule():
    # What a hack
    import rich.rule  # noqa: F401

    yield


def get_fn_name(fn: Callable[..., Any]) -> str:
    return fn.__name__  # ty: ignore[unresolved-attribute]


@pytest.fixture
def worker_id(request):
    """Get the xdist worker ID, or 'master' if not using xdist."""
    return getattr(request.config, "workerinput", {}).get("workerid", "master")


@pytest.fixture
def free_port():
    """Get a free port for the test to use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def free_port_factory(worker_id):
    """Factory to get free ports that tracks used ports per test session."""
    used_ports = set()

    def get_port():
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                s.listen(1)
                port = s.getsockname()[1]
                if port not in used_ports:
                    used_ports.add(port)
                    return port

    return get_port
