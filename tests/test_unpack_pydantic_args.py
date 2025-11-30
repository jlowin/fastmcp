import pytest
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


def test_unpack_pydantic_args_collision():
    mcp = FastMCP("test")

    class User(BaseModel):
        name: str

    class Admin(BaseModel):
        name: str

    # Should raise ValueError due to duplicate 'name' field
    with pytest.raises(
        ValueError, match="Field name 'name' from Pydantic model 'Admin' conflicts"
    ):

        @mcp.tool(unpack_pydantic_args=True)
        def process(user: User, admin: Admin):
            pass


def test_unpack_pydantic_args_collision_with_arg():
    mcp = FastMCP("test")

    class User(BaseModel):
        name: str

    # Should raise ValueError due to duplicate 'name' field
    with pytest.raises(
        ValueError, match="Field name 'name' from Pydantic model 'User' conflicts"
    ):

        @mcp.tool(unpack_pydantic_args=True)
        def greet(name: str, user: User):
            pass


def test_unpack_pydantic_args_default_factory():
    mcp = FastMCP("test")

    def generate_id():
        return "123"

    class Item(BaseModel):
        id: str = Field(default_factory=generate_id)
        name: str

    @mcp.tool(unpack_pydantic_args=True)
    def create_item(item: Item) -> str:
        return f"{item.id}:{item.name}"

    tool = mcp._tool_manager._tools["create_item"]
    schema = tool.parameters

    # id should be required in schema because factory can't be represented statically
    assert "id" in schema["required"]
    assert "name" in schema["required"]

    import asyncio

    # User provides id
    result = asyncio.run(tool.run({"id": "custom", "name": "test"}))
    assert result.content[0].text == "custom:test"
