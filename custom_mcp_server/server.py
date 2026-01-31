"""
Custom MCP Server - Runs locally (STDIO) and on web (HTTP)

Usage:
    Local (STDIO):  uv run python server.py
    Web (HTTP):     uv run python server.py --http --port 8000
"""

import argparse
import datetime
import os
import subprocess
import sys
from typing import Any

from fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    "CustomMCP",
    instructions="A custom MCP server with system, file, and utility tools.",
)


# ============================================================================
# SYSTEM TOOLS - Information about the environment
# ============================================================================


@mcp.tool
def get_system_info() -> dict[str, Any]:
    """Get current system information including OS, Python version, and time."""
    return {
        "os": os.name,
        "platform": sys.platform,
        "python_version": sys.version,
        "cwd": os.getcwd(),
        "timestamp": datetime.datetime.now().isoformat(),
        "env_vars_count": len(os.environ),
    }


@mcp.tool
def get_env_var(name: str) -> str | None:
    """Get an environment variable value (safe subset only)."""
    safe_vars = {"PATH", "HOME", "USER", "SHELL", "PWD", "LANG", "TERM"}
    if name.upper() in safe_vars:
        return os.environ.get(name)
    return f"Access to '{name}' is restricted for security."


# ============================================================================
# FILE TOOLS - Read and list files
# ============================================================================


@mcp.tool
def list_directory(path: str = ".") -> list[dict[str, Any]]:
    """List files and directories at the given path."""
    entries = []
    try:
        for entry in os.scandir(path):
            entries.append({
                "name": entry.name,
                "is_file": entry.is_file(),
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            })
    except PermissionError:
        return [{"error": "Permission denied"}]
    except FileNotFoundError:
        return [{"error": f"Path not found: {path}"}]
    return sorted(entries, key=lambda x: (not x.get("is_dir", False), x["name"]))


@mcp.tool
def read_file(path: str, max_lines: int = 100) -> dict[str, Any]:
    """Read a text file (limited to max_lines for safety)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[:max_lines]
        return {
            "path": path,
            "lines_read": len(lines),
            "truncated": len(lines) == max_lines,
            "content": "".join(lines),
        }
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}
    except PermissionError:
        return {"error": "Permission denied"}
    except UnicodeDecodeError:
        return {"error": "File is not valid UTF-8 text"}


# ============================================================================
# UTILITY TOOLS - Helpful utilities
# ============================================================================


@mcp.tool
def run_command(command: str) -> dict[str, Any]:
    """Run a safe shell command (limited to read-only operations)."""
    safe_commands = {"ls", "pwd", "whoami", "date", "uname", "cat", "head", "tail", "wc"}
    cmd_base = command.split()[0] if command else ""

    if cmd_base not in safe_commands:
        return {"error": f"Command '{cmd_base}' not in allowed list: {safe_commands}"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def calculate(expression: str) -> dict[str, Any]:
    """Safely evaluate a mathematical expression."""
    allowed_chars = set("0123456789+-*/.() ")
    if not all(c in allowed_chars for c in expression):
        return {"error": "Invalid characters in expression"}

    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": f"Calculation failed: {e}"}


# ============================================================================
# RESOURCES - Static data endpoints
# ============================================================================


@mcp.resource("custom://status")
def server_status() -> dict[str, Any]:
    """Current server status and health."""
    return {
        "status": "healthy",
        "uptime": "running",
        "timestamp": datetime.datetime.now().isoformat(),
        "tools_available": 6,
    }


@mcp.resource("custom://config")
def server_config() -> dict[str, Any]:
    """Server configuration (non-sensitive)."""
    return {
        "name": "CustomMCP",
        "version": "1.0.0",
        "transports": ["stdio", "http"],
        "max_file_lines": 100,
        "command_timeout": 10,
    }


# ============================================================================
# PROMPTS - Reusable prompt templates
# ============================================================================


@mcp.prompt("analyze_file")
def analyze_file_prompt(file_path: str) -> str:
    """Prompt to analyze a file's contents."""
    return f"""Please analyze the file at '{file_path}':
1. Read the file using the read_file tool
2. Summarize its contents
3. Identify the file type and purpose
4. Note any interesting patterns or issues"""


@mcp.prompt("system_check")
def system_check_prompt() -> str:
    """Prompt to perform a system health check."""
    return """Please perform a system health check:
1. Get system info using get_system_info
2. List the current directory
3. Report any issues or anomalies
4. Provide recommendations if needed"""


# ============================================================================
# MAIN - Support both STDIO and HTTP transports
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Custom MCP Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    args = parser.parse_args()

    if args.http:
        # Run as HTTP server (web accessible)
        print(f"Starting HTTP server on {args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        # Run as STDIO server (local)
        mcp.run()
