#!/usr/bin/env python3

"""Test script to check if input schemas contain titles that need pruning."""

import asyncio

from pydantic import BaseModel

from fastmcp import FastMCP
from fastmcp.client import Client


class InputModel(BaseModel):
    """A model with titles to test."""

    name: str
    age: int


def main():
    # Create a FastMCP server
    server = FastMCP("TestServer")

    # Create a tool with a parameter type that has titles
    @server.tool
    def process_user(user: InputModel) -> str:
        """Process a user."""
        return f"Processed {user.name}, age {user.age}"

    async def test():
        # Connect to the server and inspect the tool schema
        async with Client(server) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "process_user")

            print("Tool input schema:")
            import json

            print(json.dumps(tool.inputSchema, indent=2))

            # Check for titles
            def has_titles(obj):
                if isinstance(obj, dict):
                    if "title" in obj:
                        return True
                    return any(has_titles(v) for v in obj.values())
                elif isinstance(obj, list):
                    return any(has_titles(item) for item in obj)
                return False

            if tool.inputSchema and has_titles(tool.inputSchema):
                print("\n✓ Input schema contains titles that should be pruned")
                return True
            else:
                print("\n✗ No titles found in input schema")
                return False

    return asyncio.run(test())


if __name__ == "__main__":
    found_titles = main()
    exit(0 if found_titles else 1)
