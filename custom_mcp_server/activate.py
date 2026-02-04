#!/usr/bin/env python
"""
MCP Server Activation CLI - Wire up and activate MCP servers

Usage:
    # List all servers and their status
    uv run python custom_mcp_server/activate.py --list

    # Test connection to specific servers
    uv run python custom_mcp_server/activate.py --test custom echo

    # Test all enabled servers
    uv run python custom_mcp_server/activate.py --test-all

    # Generate Claude Desktop config
    uv run python custom_mcp_server/activate.py --claude-desktop

    # Run a server in HTTP mode
    uv run python custom_mcp_server/activate.py --serve custom --port 8000

    # Interactive multi-server client
    uv run python custom_mcp_server/activate.py --connect custom teamwork notion
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import Client, FastMCP

from mcp_registry import (
    MCP_SERVERS,
    ServerType,
    UseCase,
    auto_enable_servers,
    build_multi_server_config,
    get_enabled_servers,
    get_servers_by_use_case,
    print_registry,
)

# Auto-enable servers based on available environment variables
auto_enable_servers()


async def test_server(name: str) -> tuple[str, bool, str]:
    """Test connection to a single MCP server."""
    if name not in MCP_SERVERS:
        return name, False, f"Unknown server: {name}"

    config = MCP_SERVERS[name]

    if not config.enabled:
        return name, False, "Server is disabled"

    try:
        # Determine connection source
        if config.server_type == ServerType.LOCAL_STDIO:
            source = config.script_path
        elif config.server_type in (ServerType.LOCAL_HTTP, ServerType.REMOTE_HTTP):
            source = config.http_url
        elif config.server_type == ServerType.NPX:
            source = config.to_client_config()
        else:
            return name, False, f"Unsupported server type: {config.server_type}"

        # Try to connect
        async with Client(source, timeout=10.0) as client:
            await client.ping()
            tools = await client.list_tools()
            return name, True, f"OK - {len(tools)} tools available"

    except Exception as e:
        return name, False, str(e)[:100]


async def test_all_servers():
    """Test all enabled servers."""
    print("\n🔍 Testing MCP Server Connections...\n")

    enabled = get_enabled_servers()
    if not enabled:
        print("No servers enabled!")
        return

    results = await asyncio.gather(*[
        test_server(name) for name in enabled.keys()
    ])

    print("-" * 60)
    for name, success, message in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}: {message}")
    print("-" * 60)

    passed = sum(1 for _, success, _ in results if success)
    print(f"\n{passed}/{len(results)} servers connected successfully")


async def test_specific_servers(names: list[str]):
    """Test specific servers."""
    print(f"\n🔍 Testing servers: {', '.join(names)}\n")

    results = await asyncio.gather(*[test_server(name) for name in names])

    for name, success, message in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}: {message}")


def generate_claude_desktop_config():
    """Generate configuration for Claude Desktop."""
    config = {"mcpServers": {}}

    for name, server in MCP_SERVERS.items():
        if not server.enabled:
            continue

        if server.server_type == ServerType.LOCAL_STDIO:
            config["mcpServers"][name] = {
                "command": "uv",
                "args": ["run", "python", server.script_path],
                "cwd": str(Path(__file__).parent.parent),
            }
        elif server.server_type == ServerType.NPX:
            config["mcpServers"][name] = {
                "command": "npx",
                "args": [server.npx_package],
                "env": {k: v for k, v in server.env_vars.items()
                       if not v.startswith("${")},
            }

    print("\n📋 Claude Desktop Configuration")
    print("=" * 60)
    print("Add to: ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("=" * 60)
    print(json.dumps(config, indent=2))
    print("=" * 60)


async def serve_server(name: str, port: int):
    """Run a server in HTTP mode."""
    if name not in MCP_SERVERS:
        print(f"❌ Unknown server: {name}")
        return

    config = MCP_SERVERS[name]

    if config.server_type != ServerType.LOCAL_STDIO:
        print(f"❌ Server '{name}' cannot be run in HTTP mode")
        return

    print(f"🚀 Starting {name} on http://0.0.0.0:{port}/mcp")

    # Import and run the server
    script_path = Path(__file__).parent.parent / config.script_path
    spec = __import__("importlib.util").util.spec_from_file_location("server", script_path)
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, "mcp"):
        module.mcp.run(transport="http", host="0.0.0.0", port=port)
    else:
        print(f"❌ No 'mcp' server found in {script_path}")


async def interactive_client(server_names: list[str]):
    """Run an interactive multi-server client session."""
    print(f"\n🔗 Connecting to servers: {', '.join(server_names)}")

    config = build_multi_server_config(server_names)

    if not config["mcpServers"]:
        print("❌ No valid servers to connect to")
        return

    try:
        async with Client(config) as client:
            print("✅ Connected!\n")

            # List all tools
            tools = await client.list_tools()
            print(f"📦 Available tools ({len(tools)}):")
            for tool in tools[:20]:  # Show first 20
                print(f"   - {tool.name}: {tool.description[:60] if tool.description else 'No description'}...")

            if len(tools) > 20:
                print(f"   ... and {len(tools) - 20} more")

            print("\n💡 Use FastMCP Client in your code:")
            print(f"   async with Client({json.dumps(config, indent=2)}) as client:")
            print("       result = await client.call_tool('tool_name', {'arg': 'value'})")

    except Exception as e:
        print(f"❌ Connection failed: {e}")


def list_by_use_case():
    """List servers grouped by use case."""
    print("\n📂 MCP Servers by Use Case\n")

    for use_case in UseCase:
        servers = get_servers_by_use_case(use_case)
        if servers:
            print(f"  {use_case.value.upper()}:")
            for s in servers:
                print(f"    - {s.name}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Activ8-AI MCP Server Activation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--list", "-l", action="store_true",
                       help="List all registered MCP servers")
    parser.add_argument("--use-cases", "-u", action="store_true",
                       help="List servers grouped by use case")
    parser.add_argument("--test", "-t", nargs="+", metavar="SERVER",
                       help="Test specific server connections")
    parser.add_argument("--test-all", "-T", action="store_true",
                       help="Test all enabled server connections")
    parser.add_argument("--claude-desktop", "-c", action="store_true",
                       help="Generate Claude Desktop configuration")
    parser.add_argument("--serve", "-s", metavar="SERVER",
                       help="Run a server in HTTP mode")
    parser.add_argument("--port", "-p", type=int, default=8000,
                       help="Port for HTTP server (default: 8000)")
    parser.add_argument("--connect", nargs="+", metavar="SERVER",
                       help="Connect to servers interactively")

    args = parser.parse_args()

    # Default to --list if no args
    if len(sys.argv) == 1:
        args.list = True

    if args.list:
        print_registry()
    elif args.use_cases:
        list_by_use_case()
    elif args.test:
        asyncio.run(test_specific_servers(args.test))
    elif args.test_all:
        asyncio.run(test_all_servers())
    elif args.claude_desktop:
        generate_claude_desktop_config()
    elif args.serve:
        asyncio.run(serve_server(args.serve, args.port))
    elif args.connect:
        asyncio.run(interactive_client(args.connect))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
