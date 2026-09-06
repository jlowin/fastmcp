"""Tests for HTTP server lifespan teardown on process signals (SIGTERM / SIGINT).

Regression test for Issue #4927: Docker, Kubernetes, and Cloud Run terminate
containers with SIGTERM. The lifespan teardown must execute before the process
exits so that connections, buffers, and background tasks are cleanly finalized.
"""

import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fastmcp.utilities.tests import find_available_port

SERVER_SCRIPT = """
import sys
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

events_file = Path(sys.argv[1])
port = int(sys.argv[2])

def log_event(name: str):
    with events_file.open("a") as f:
        f.write(name + "\\n")

@lifespan
async def server_lifespan(server):
    log_event("startup")
    yield {"db": "connected"}
    log_event("shutdown")

mcp = FastMCP("SignalTestServer", lifespan=server_lifespan)

@mcp.tool
def ping() -> str:
    return "pong"

if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=port, show_banner=False)
"""


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_http_server_lifespan_teardown_on_signal(tmp_path: Path, sig: signal.Signals):
    """Lifespan teardown must run when the server process receives SIGTERM or SIGINT."""
    events_file = tmp_path / "events.txt"
    server_script = tmp_path / "server.py"
    server_script.write_text(SERVER_SCRIPT)

    port = find_available_port()
    proc = subprocess.Popen(
        [sys.executable, str(server_script), str(events_file), str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for the startup event to be recorded
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if events_file.exists() and "startup" in events_file.read_text():
            break
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                f"Server exited prematurely with code {proc.returncode}:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
            )
        time.sleep(0.05)
    else:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise TimeoutError(f"Server did not log startup within timeout.\nSTDOUT: {stdout}\nSTDERR: {stderr}")

    # Send the signal
    proc.send_signal(sig)

    # Wait for process termination
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise TimeoutError(f"Server did not exit within timeout after {sig.name}.\nSTDOUT: {stdout}\nSTDERR: {stderr}")

    # Assert that teardown ran
    events = events_file.read_text().splitlines()
    assert "startup" in events
    assert "shutdown" in events
