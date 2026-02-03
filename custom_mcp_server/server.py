"""
Custom MCP Server - Runs locally (STDIO) and on web (HTTP)

Usage:
    Local (STDIO):  uv run python server.py
    Web (HTTP):     uv run python server.py --http --port 8000
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
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
# GIT TOOLS - Repository information
# ============================================================================


@mcp.tool
def git_status(path: str = ".") -> dict[str, Any]:
    """Get git repository status including branch, changes, and recent commits."""
    try:
        # Get current branch
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path, capture_output=True, text=True, timeout=10
        )
        # Get status
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path, capture_output=True, text=True, timeout=10
        )
        # Get recent commits
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=path, capture_output=True, text=True, timeout=10
        )
        # Get remote URL
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path, capture_output=True, text=True, timeout=10
        )

        changes = status.stdout.strip().split("\n") if status.stdout.strip() else []
        return {
            "branch": branch.stdout.strip(),
            "remote": remote.stdout.strip() if remote.returncode == 0 else None,
            "changes_count": len(changes),
            "changes": changes[:10],  # Limit to 10
            "recent_commits": log.stdout.strip().split("\n") if log.stdout.strip() else [],
            "is_clean": len(changes) == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out"}
    except FileNotFoundError:
        return {"error": "Git not found or not a git repository"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def git_diff(path: str = ".", staged: bool = False) -> dict[str, Any]:
    """Get git diff output (staged or unstaged changes)."""
    try:
        cmd = ["git", "diff", "--stat"]
        if staged:
            cmd.append("--staged")

        result = subprocess.run(
            cmd, cwd=path, capture_output=True, text=True, timeout=10
        )
        return {
            "staged": staged,
            "diff_stat": result.stdout.strip(),
            "has_changes": bool(result.stdout.strip()),
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# SEARCH TOOLS - Find files and content
# ============================================================================


@mcp.tool
def search_files(
    pattern: str,
    path: str = ".",
    file_pattern: str = "*",
    max_results: int = 50
) -> dict[str, Any]:
    """Search for text pattern in files (like grep)."""
    results = []
    try:
        base_path = Path(path)
        for file_path in base_path.rglob(file_pattern):
            if file_path.is_file() and len(results) < max_results:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(content.split("\n"), 1):
                        if pattern.lower() in line.lower():
                            results.append({
                                "file": str(file_path),
                                "line": i,
                                "content": line.strip()[:200],
                            })
                            if len(results) >= max_results:
                                break
                except Exception:
                    continue

        return {
            "pattern": pattern,
            "matches": len(results),
            "truncated": len(results) >= max_results,
            "results": results,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def find_files(
    pattern: str,
    path: str = ".",
    max_results: int = 100
) -> dict[str, Any]:
    """Find files matching a glob pattern."""
    try:
        base_path = Path(path)
        files = list(base_path.rglob(pattern))[:max_results]
        return {
            "pattern": pattern,
            "count": len(files),
            "files": [str(f) for f in files],
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# JSON/DATA TOOLS - Parse and manipulate data
# ============================================================================


@mcp.tool
def parse_json(content: str) -> dict[str, Any]:
    """Parse JSON string and return structured data."""
    try:
        data = json.loads(content)
        return {
            "valid": True,
            "type": type(data).__name__,
            "data": data,
        }
    except json.JSONDecodeError as e:
        return {"valid": False, "error": str(e)}


@mcp.tool
def format_json(content: str, indent: int = 2) -> dict[str, Any]:
    """Format/prettify JSON string."""
    try:
        data = json.loads(content)
        formatted = json.dumps(data, indent=indent, sort_keys=True)
        return {"formatted": formatted}
    except json.JSONDecodeError as e:
        return {"error": str(e)}


# ============================================================================
# HTTP TOOLS - Make HTTP requests
# ============================================================================


@mcp.tool
def http_get(url: str, timeout: int = 10) -> dict[str, Any]:
    """Make an HTTP GET request and return the response."""
    # Only allow http/https
    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CustomMCP/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8", errors="ignore")
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "content_length": len(content),
                "content": content[:5000],  # Limit response size
                "truncated": len(content) > 5000,
            }
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def check_url(url: str, timeout: int = 5) -> dict[str, Any]:
    """Check if a URL is reachable (HEAD request)."""
    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://"}

    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "CustomMCP/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return {
                "reachable": True,
                "status": response.status,
                "content_type": response.headers.get("Content-Type"),
            }
    except Exception as e:
        return {"reachable": False, "error": str(e)}


# ============================================================================
# TEXT TOOLS - Text manipulation
# ============================================================================


@mcp.tool
def text_stats(text: str) -> dict[str, Any]:
    """Get statistics about a text string."""
    lines = text.split("\n")
    words = text.split()
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(lines),
        "non_empty_lines": len([l for l in lines if l.strip()]),
        "unique_words": len(set(w.lower() for w in words)),
    }


@mcp.tool
def regex_search(text: str, pattern: str, flags: str = "") -> dict[str, Any]:
    """Search text using a regular expression."""
    try:
        re_flags = 0
        if "i" in flags:
            re_flags |= re.IGNORECASE
        if "m" in flags:
            re_flags |= re.MULTILINE

        matches = re.findall(pattern, text, re_flags)
        return {
            "pattern": pattern,
            "matches": len(matches),
            "results": matches[:50],  # Limit results
        }
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}


@mcp.tool
def hash_text(text: str, algorithm: str = "sha256") -> dict[str, Any]:
    """Generate hash of text using specified algorithm."""
    algorithms = {"md5", "sha1", "sha256", "sha512"}
    if algorithm not in algorithms:
        return {"error": f"Algorithm must be one of: {algorithms}"}

    h = hashlib.new(algorithm)
    h.update(text.encode("utf-8"))
    return {
        "algorithm": algorithm,
        "hash": h.hexdigest(),
    }


# ============================================================================
# NETWORK TOOLS - Network diagnostics
# ============================================================================


@mcp.tool
def check_port(host: str, port: int, timeout: int = 3) -> dict[str, Any]:
    """Check if a TCP port is open on a host."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return {
            "host": host,
            "port": port,
            "open": result == 0,
        }
    except socket.gaierror:
        return {"error": f"Could not resolve host: {host}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def dns_lookup(hostname: str) -> dict[str, Any]:
    """Perform DNS lookup for a hostname."""
    try:
        ip = socket.gethostbyname(hostname)
        return {
            "hostname": hostname,
            "ip": ip,
            "resolved": True,
        }
    except socket.gaierror as e:
        return {"hostname": hostname, "resolved": False, "error": str(e)}


# ============================================================================
# DATETIME TOOLS - Date and time utilities
# ============================================================================


@mcp.tool
def current_time(timezone: str = "UTC") -> dict[str, Any]:
    """Get current date and time."""
    now = datetime.datetime.now()
    utc_now = datetime.datetime.utcnow()
    return {
        "local": now.isoformat(),
        "utc": utc_now.isoformat(),
        "timestamp": int(now.timestamp()),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
    }


@mcp.tool
def parse_timestamp(timestamp: int) -> dict[str, Any]:
    """Convert Unix timestamp to datetime."""
    try:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return {
            "timestamp": timestamp,
            "datetime": dt.isoformat(),
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
        }
    except (ValueError, OSError) as e:
        return {"error": str(e)}


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
        "tools_available": 21,  # Updated tool count
    }


@mcp.resource("custom://config")
def server_config() -> dict[str, Any]:
    """Server configuration (non-sensitive)."""
    return {
        "name": "CustomMCP",
        "version": "2.0.0",
        "transports": ["stdio", "http"],
        "max_file_lines": 100,
        "command_timeout": 10,
        "tool_categories": [
            "system", "file", "utility", "git",
            "search", "json", "http", "text",
            "network", "datetime"
        ],
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
