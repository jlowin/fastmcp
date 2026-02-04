#!/usr/bin/env python
"""
Activ8-AI MCP Command Line Interface

Commands:
    activ8-mcp serve              Run the MCP server (STDIO)
    activ8-mcp serve --http       Run as HTTP server
    activ8-mcp list               List all registered servers
    activ8-mcp test [SERVER]      Test server connections
    activ8-mcp config             Generate Claude Desktop config
"""

import argparse
import asyncio
import json
import sys

from activ8_mcp.server import mcp, main as server_main
from activ8_mcp.registry import (
    MCP_REGISTRY,
    UseCase,
    get_enabled_servers,
    get_servers_by_use_case,
    print_registry,
    generate_claude_desktop_config,
    check_server_secrets,
)


def cmd_serve(args):
    """Run the MCP server."""
    sys.argv = ["activ8-mcp"]
    if args.http:
        sys.argv.extend(["--http", "--port", str(args.port)])
        if args.host:
            sys.argv.extend(["--host", args.host])
    server_main()


def cmd_list(args):
    """List all registered servers."""
    if args.use_case:
        print(f"\nServers for use case: {args.use_case}\n")
        try:
            use_case = UseCase(args.use_case)
            servers = get_servers_by_use_case(use_case)
            for server in servers:
                print(f"  - {server.name}: {server.description}")
        except ValueError:
            print(f"Unknown use case: {args.use_case}")
            print(f"Valid use cases: {[uc.value for uc in UseCase]}")
    else:
        print_registry()


async def test_server_connection(name: str) -> tuple[str, bool, str]:
    """Test connection to a server."""
    from fastmcp import Client

    if name not in MCP_REGISTRY:
        return name, False, f"Unknown server: {name}"

    server = MCP_REGISTRY[name]

    if not server.enabled:
        return name, False, "Server is disabled"

    # Check secrets
    ok, missing = check_server_secrets(name)
    if not ok:
        return name, False, f"Missing secrets: {', '.join(missing)}"

    return name, True, f"Ready ({server.tools_count} tools)"


async def cmd_test_async(args):
    """Test server connections."""
    servers = args.servers if args.servers else list(get_enabled_servers().keys())

    print(f"\nTesting servers: {', '.join(servers)}\n")

    results = await asyncio.gather(*[test_server_connection(s) for s in servers])

    for name, success, message in results:
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {name}: {message}")

    passed = sum(1 for _, success, _ in results if success)
    print(f"\n{passed}/{len(results)} servers ready")


def cmd_test(args):
    """Test server connections (sync wrapper)."""
    asyncio.run(cmd_test_async(args))


def cmd_config(args):
    """Generate Claude Desktop configuration."""
    config = generate_claude_desktop_config()

    print("\nClaude Desktop Configuration")
    print("=" * 60)
    print("Add to: ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("=" * 60)
    print(json.dumps(config, indent=2))
    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Activ8-AI MCP Server CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Run the MCP server")
    serve_parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    serve_parser.add_argument("--port", type=int, default=8000, help="HTTP port")
    serve_parser.add_argument("--host", default="0.0.0.0", help="HTTP host")

    # list command
    list_parser = subparsers.add_parser("list", help="List registered servers")
    list_parser.add_argument("--use-case", "-u", help="Filter by use case")

    # test command
    test_parser = subparsers.add_parser("test", help="Test server connections")
    test_parser.add_argument("servers", nargs="*", help="Servers to test (default: all enabled)")

    # config command
    subparsers.add_parser("config", help="Generate Claude Desktop config")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "config":
        cmd_config(args)
    else:
        # Default: run server in STDIO mode
        mcp.run()


if __name__ == "__main__":
    main()
