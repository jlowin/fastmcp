"""Example usage of CompatibilityTools contrib module."""

import asyncio

from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.contrib.compatibility_tools import add_compatibility_tools

# Create a server with some resources and prompts
mcp = FastMCP("Example Server")


@mcp.resource("config://settings")
def get_settings() -> str:
    """Server configuration data."""
    return "Server configuration: enabled=true, timeout=30s"


@mcp.resource("data://users")
def get_users() -> str:
    """User data."""
    return "Users: alice, bob, charlie"


@mcp.prompt()
def greeting(name: str) -> str:
    """Generate a greeting message."""
    return f"Hello, {name}! Welcome to the server."


@mcp.prompt()
def system_prompt(context: str) -> str:
    """Generate a system prompt."""
    return f"You are a helpful assistant. Context: {context}"


# Register compatibility tools
add_compatibility_tools(mcp)


# Test the tools
async def main() -> None:
    async with Client(mcp) as client:
        # List all tools (should include compatibility tools)
        tools = await client.list_tools()
        print("\n=== Available Tools ===")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")

        # Use list_resources tool
        print("\n=== Resources (via tool) ===")
        resources = await client.call_tool("list_resources", {})
        for resource in resources.structured_content["resources"]:  # type: ignore[index]
            print(f"  - {resource['uri']}: {resource['name']}")

        # Use get_resource tool
        print("\n=== Get Resource (via tool) ===")
        resource_content = await client.call_tool(
            "get_resource", {"uri": "config://settings"}
        )
        contents = resource_content.structured_content["contents"]  # type: ignore[index]
        print(
            f"  {contents[0]['uri']}: {contents[0].get('text', contents[0].get('blob'))}"
        )

        # Use list_prompts tool
        print("\n=== Prompts (via tool) ===")
        prompts = await client.call_tool("list_prompts", {})
        for prompt in prompts.structured_content["prompts"]:  # type: ignore[index]
            print(
                f"  - {prompt['name']}: {prompt.get('description', 'No description')}"
            )

        # Use get_prompt tool
        print("\n=== Get Prompt (via tool) ===")
        prompt_result = await client.call_tool(
            "get_prompt", {"name": "greeting", "arguments": {"name": "World"}}
        )
        messages = prompt_result.structured_content["messages"]  # type: ignore[index]
        for msg in messages:
            print(f"  {msg['role']}: {msg['content']}")


if __name__ == "__main__":
    asyncio.run(main())
