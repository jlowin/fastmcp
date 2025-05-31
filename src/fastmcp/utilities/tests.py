from __future__ import annotations

import copy
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

from fastmcp.settings import settings
from fastmcp.utilities.http import find_available_port


@contextmanager
def temporary_settings(**kwargs: Any):
    """
    Temporarily override ControlFlow setting values.

    Args:
        **kwargs: The settings to override, including nested settings.

    Example:
        Temporarily override a setting:
        ```python
        import fastmcp
        from fastmcp.utilities.tests import temporary_settings

        with temporary_settings(log_level='DEBUG'):
            assert fastmcp.settings.settings.log_level == 'DEBUG'
        assert fastmcp.settings.settings.log_level == 'INFO'
        ```
    """
    old_settings = copy.deepcopy(settings.model_dump())

    try:
        # apply the new settings
        for attr, value in kwargs.items():
            if not hasattr(settings, attr):
                raise AttributeError(f"Setting {attr} does not exist.")
            setattr(settings, attr, value)
        yield

    finally:
        # restore the old settings
        for attr in kwargs:
            if hasattr(settings, attr):
                setattr(settings, attr, old_settings[attr])


def _run_server_wrapper(server_fn: Callable[..., None], host: str, port: int, *args):
    """
    Wrapper function to run the server function and handle errors.
    This runs in the subprocess.
    """
    try:
        server_fn(host, port, *args)
    except Exception as e:
        print(f"Server function failed with error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


@contextmanager
def run_server_in_process(
    server_fn: Callable[..., None], *args
) -> Generator[str, None, None]:
    """
    Context manager that runs a server function in a separate process and returns the
    server URL. When the context manager is exited, the server process is killed.

    Args:
        server_fn: The server function to run.
        *args: Additional arguments to pass to the server function.

    Returns:
        The server URL.
    """
    host = "127.0.0.1"
    port = find_available_port()

    # Create a subprocess that runs the server function
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"""
import sys
import traceback
from importlib import import_module

# Import the server function
module_name = "{server_fn.__module__}"
function_name = "{server_fn.__name__}"

try:
    module = import_module(module_name)
    server_fn = getattr(module, function_name)
    server_fn("{host}", {port}, *{args!r})
except Exception as e:
    print(f"Server function failed with error: {{e}}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
""",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to be running
    max_attempts = 10
    attempt = 0
    while attempt < max_attempts and proc.poll() is None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
                break
        except ConnectionRefusedError:
            if attempt < 3:
                time.sleep(0.01)
            else:
                time.sleep(0.1)
            attempt += 1
    else:
        # Check if process died during startup
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            if stdout:
                print(f"Server stdout: {stdout}", file=sys.stdout)
            if stderr:
                print(f"Server stderr: {stderr}", file=sys.stderr)
            print(
                f"Server process died during startup with exit code: {proc.returncode}",
                file=sys.stderr,
            )
        raise RuntimeError(f"Server failed to start after {max_attempts} attempts")

    try:
        yield f"http://{host}:{port}"
    finally:
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
            if stdout:
                print(f"Server stdout: {stdout}", file=sys.stdout)
            if stderr:
                print(f"Server stderr: {stderr}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=2)
                if stdout:
                    print(f"Server stdout: {stdout}", file=sys.stdout)
                if stderr:
                    print(f"Server stderr: {stderr}", file=sys.stderr)
            except subprocess.TimeoutExpired:
                print(
                    "Server process failed to terminate even after kill",
                    file=sys.stderr,
                )
                raise RuntimeError("Server process failed to terminate even after kill")

        # If the process ended with a non-zero exit code, report it
        if proc.returncode != 0:
            print(
                f"Server process ended with exit code: {proc.returncode}",
                file=sys.stderr,
            )
