"""Process-level regression tests for graceful signal shutdown."""

from __future__ import annotations

import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX signal semantics are required"
)

SERVER_MODULE = "tests.server.signal_shutdown_server"
PROCESS_TIMEOUT = 10.0


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_http(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + PROCESS_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("HTTP server exited before accepting connections")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("HTTP server did not accept connections")


@pytest.mark.timeout(20)
@pytest.mark.parametrize("transport", ["http", "sse"])
@pytest.mark.parametrize(
    "shutdown_signal", [signal.SIGINT, signal.SIGTERM], ids=["sigint", "sigterm"]
)
def test_signal_runs_lifespan_teardown_and_exits(
    tmp_path: Path, transport: str, shutdown_signal: signal.Signals
) -> None:
    """A normal container stop must release resources and finish promptly.

    The readiness checks are transport-level rather than lifespan-level. This
    prevents a false pass caused by signaling HTTP before Uvicorn installs its
    handlers. The teardown itself awaits before writing its marker, so this
    also verifies that asynchronous cleanup is allowed to finish.
    """
    events_path = tmp_path / "events.txt"
    port = _available_port()
    command = [
        sys.executable,
        "-m",
        SERVER_MODULE,
        "--events",
        str(events_path),
        "--port",
        str(port),
        "--transport",
        transport,
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        _wait_for_http(port, process)

        process.send_signal(shutdown_signal)
        try:
            process.wait(timeout=PROCESS_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            pytest.fail(
                f"{transport} server did not exit after {shutdown_signal.name}; "
                f"stdout={stdout!r}, stderr={stderr!r}"
            )

        stdout, stderr = process.communicate()
        events = events_path.read_text().splitlines()
        assert events == ["startup", "shutdown"], (
            f"transport={transport}, signal={shutdown_signal.name}, "
            f"returncode={process.returncode}, stdout={stdout!r}, stderr={stderr!r}"
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
