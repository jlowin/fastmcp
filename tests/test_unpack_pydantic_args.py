from pydantic import BaseModel, Field
from fastmcp import FastMCP


class User(BaseModel):
    name: str = Field(description="The user's name")
    age: int = Field(description="The user's age")


def test_unpack_pydantic_args():
    mcp = FastMCP("test")

    @mcp.tool(unpack_pydantic_args=True)
    def greet_user(user: User, greeting: str = "Hello") -> str:
        return f"{greeting}, {user.name}! You are {user.age} years old."

    tool = mcp._tool_manager._tools["greet_user"]

    # Check schema
    schema = tool.parameters
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]
    assert "greeting" in schema["properties"]
    assert "user" not in schema["properties"]

    # Check required fields
    assert "name" in schema["required"]
    assert "age" in schema["required"]
    assert "greeting" not in schema.get("required", [])

    # Run tool
    import asyncio

    result = asyncio.run(tool.run({"name": "Alice", "age": 30, "greeting": "Hi"}))

    assert result.content[0].text == "Hi, Alice! You are 30 years old."


def test_unpack_pydantic_args_nested():
    mcp = FastMCP("test")

    class Address(BaseModel):
        city: str
        zipcode: str

    class UserWithAddress(BaseModel):
        name: str
        address: Address

    # This feature currently only unpacks top-level Pydantic models.
    # Nested models inside Pydantic models are kept as is (Pydantic handles them).

    @mcp.tool(unpack_pydantic_args=True)
    def process_address(address: Address) -> str:
        return f"{address.city} {address.zipcode}"

    tool = mcp._tool_manager._tools["process_address"]
    schema = tool.parameters

    assert "city" in schema["properties"]
    assert "zipcode" in schema["properties"]

    import asyncio

    result = asyncio.run(tool.run({"city": "New York", "zipcode": "10001"}))
    assert result.content[0].text == "New York 10001"
