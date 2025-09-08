#!/usr/bin/env python3

"""Test script to check if output schemas contain titles that need pruning."""

import asyncio

from pydantic import BaseModel

from fastmcp import FastMCP
from fastmcp.client import Client


class OutputModel(BaseModel):
    """A model with titles to test."""

    name: str
    age: int


def main():
    # Create a FastMCP server
    server = FastMCP("TestServer")

    # Create a tool with a return type that has titles
    @server.tool
    def get_user() -> OutputModel:
        """Get a user."""
        return OutputModel(name="Alice", age=30)

    async def test():
        # Connect to the server and inspect the tool schema
        async with Client(server) as client:
            tools = await client.list_tools()
            tool = next(t for t in tools if t.name == "get_user")

            print("Tool output schema:")
            import json

            print(json.dumps(tool.outputSchema, indent=2))

            # Check for titles
            def has_titles(obj):
                if isinstance(obj, dict):
                    if "title" in obj:
                        return True
                    return any(has_titles(v) for v in obj.values())
                elif isinstance(obj, list):
                    return any(has_titles(item) for item in obj)
                return False

            if tool.outputSchema and has_titles(tool.outputSchema):
                print("\n✓ Output schema contains titles that should be pruned")
                return True
            else:
                print("\n✗ No titles found in output schema")
                return False

    return asyncio.run(test())


if __name__ == "__main__":
    found_titles = main()
    exit(0 if found_titles else 1)
