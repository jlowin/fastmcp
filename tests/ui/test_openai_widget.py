"""Tests for OpenAI widget decorator."""

from fastmcp import FastMCP


async def test_widget_decorator_basic():
    """Test basic widget decorator usage."""
    app = FastMCP("test")

    @app.ui.openai.widget
    def my_widget(x: int) -> str:
        return f"Result: {x}"

    # Widget should be registered as a tool
    tools = await app.get_tools()
    assert "my_widget" in tools
    assert tools["my_widget"].name == "my_widget"


async def test_widget_decorator_with_name():
    """Test widget decorator with custom name."""
    app = FastMCP("test")

    @app.ui.openai.widget("custom_widget")
    def my_function(x: int) -> str:
        return f"Result: {x}"

    tools = await app.get_tools()
    assert "custom_widget" in tools
    assert tools["custom_widget"].name == "custom_widget"


async def test_widget_decorator_with_name_kwarg():
    """Test widget decorator with name as keyword argument."""
    app = FastMCP("test")

    @app.ui.openai.widget(name="named_widget")
    def my_function(x: int) -> str:
        return f"Result: {x}"

    tools = await app.get_tools()
    assert "named_widget" in tools
    assert tools["named_widget"].name == "named_widget"


async def test_widget_decorator_with_description():
    """Test widget decorator with description."""
    app = FastMCP("test")

    @app.ui.openai.widget(description="This is a test widget")
    def my_widget(x: int) -> str:
        return f"Result: {x}"

    tools = await app.get_tools()
    assert "my_widget" in tools
    assert tools["my_widget"].description == "This is a test widget"


async def test_widget_decorator_with_title():
    """Test widget decorator with title."""
    app = FastMCP("test")

    @app.ui.openai.widget(title="My Widget Title")
    def my_widget(x: int) -> str:
        return f"Result: {x}"

    tools = await app.get_tools()
    assert "my_widget" in tools
    assert tools["my_widget"].title == "My Widget Title"


async def test_widget_can_be_called():
    """Test that registered widgets can be called as tools."""
    app = FastMCP("test")

    @app.ui.openai.widget
    def calculator(x: int, y: int) -> int:
        return x + y

    # Call the tool through the tool manager
    result = await app._tool_manager.call_tool("calculator", {"x": 5, "y": 3})
    assert result.content[0].text == "8"  # type: ignore[attr-defined]
