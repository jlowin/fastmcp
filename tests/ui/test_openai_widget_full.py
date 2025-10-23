"""Comprehensive tests for OpenAI widget decorator with full integration."""

import pytest

from fastmcp import FastMCP
from fastmcp.ui.openai import build_widget_tool_response


async def test_widget_with_dict_return():
    """Test widget that returns dict (structured data only)."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="test-widget",
        template_uri="ui://widget/test.html",
        html="<div>Test</div>",
    )
    def test_widget(value: str) -> dict:
        return {"value": value}

    # Tool should be registered
    tools = await app.get_tools()
    assert "test-widget" in tools

    # Call the tool
    result = await app._tool_manager.call_tool("test-widget", {"value": "hello"})

    # Should be transformed to OpenAI format (compact JSON)
    assert '"content":[]' in result.content[0].text  # type: ignore[attr-defined]
    assert '"structuredContent":{"value":"hello"}' in result.content[0].text  # type: ignore[attr-defined]


async def test_widget_with_str_return():
    """Test widget that returns str (text only)."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="text-widget",
        template_uri="ui://widget/text.html",
        html="<div>Text</div>",
    )
    def text_widget() -> str:
        return "Hello world"

    # Call the tool
    result = await app._tool_manager.call_tool("text-widget", {})

    # Should be transformed to OpenAI format with text in content (compact JSON)
    assert '"type":"text"' in result.content[0].text  # type: ignore[attr-defined]
    assert '"text":"Hello world"' in result.content[0].text  # type: ignore[attr-defined]
    assert '"content":[{' in result.content[0].text  # type: ignore[attr-defined]


async def test_widget_with_tuple_return():
    """Test widget that returns tuple (text and data)."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="combo-widget",
        template_uri="ui://widget/combo.html",
        html="<div>Combo</div>",
    )
    def combo_widget(x: int) -> tuple[str, dict]:
        return (f"Processing {x}", {"value": x, "doubled": x * 2})

    # Call the tool
    result = await app._tool_manager.call_tool("combo-widget", {"x": 5})

    # Should have both content and structuredContent (compact JSON)
    response_text = result.content[0].text  # type: ignore[attr-defined]
    assert '"text":"Processing 5"' in response_text
    assert '"structuredContent":{"value":5,"doubled":10}' in response_text


async def test_widget_with_async_function():
    """Test widget decorator works with async functions."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="async-widget",
        template_uri="ui://widget/async.html",
        html="<div>Async</div>",
    )
    async def async_widget(data: str) -> dict:
        # Simulate async operation
        import asyncio
        await asyncio.sleep(0.001)
        return {"processed": data.upper()}

    # Call the tool
    result = await app._tool_manager.call_tool("async-widget", {"data": "test"})

    # Should be transformed correctly (compact JSON)
    assert '"structuredContent":{"processed":"TEST"}' in result.content[0].text  # type: ignore[attr-defined]


async def test_widget_resource_registration():
    """Test that widget HTML is registered as a resource."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="widget-with-resource",
        template_uri="ui://widget/test-resource.html",
        html="<div id='root'>Widget HTML</div>",
        title="Test Resource Widget",
    )
    def widget_func() -> dict:
        return {}

    # Resource should be registered
    resources = await app.get_resources()
    assert "ui://widget/test-resource.html" in resources

    # Read the resource
    resource = resources["ui://widget/test-resource.html"]
    assert resource.mime_type == "text/html+skybridge"
    assert resource.name == "Test Resource Widget"


async def test_widget_metadata():
    """Test that widget has correct OpenAI metadata."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="meta-widget",
        template_uri="ui://widget/meta.html",
        html="<div>Meta</div>",
        invoking="Loading widget...",
        invoked="Widget loaded!",
    )
    def meta_widget() -> dict:
        return {}

    # Get the tool
    tools = await app.get_tools()
    tool = tools["meta-widget"]

    # Check OpenAI metadata
    assert tool.meta is not None
    assert "openai/outputTemplate" in tool.meta
    assert tool.meta["openai/outputTemplate"] == "ui://widget/meta.html"
    assert tool.meta["openai/toolInvocation/invoking"] == "Loading widget..."
    assert tool.meta["openai/toolInvocation/invoked"] == "Widget loaded!"
    assert tool.meta["openai/widgetAccessible"] is True
    assert tool.meta["openai/resultCanProduceWidget"] is True


async def test_widget_csp_configuration():
    """Test widget CSP configuration in metadata."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="csp-widget",
        template_uri="ui://widget/csp.html",
        html="<div>CSP</div>",
        widget_csp_resources=["https://custom.com", "https://another.com"],
        widget_csp_connect=["wss://websocket.com"],
    )
    def csp_widget() -> dict:
        return {}

    # Get the resource to check its metadata
    resources = await app.get_resources()
    resource = resources["ui://widget/csp.html"]

    # Check CSP in resource metadata
    assert resource.meta is not None
    assert "openai/widgetCSP" in resource.meta
    csp = resource.meta["openai/widgetCSP"]
    assert "https://custom.com" in csp["resource_domains"]
    assert "https://another.com" in csp["resource_domains"]
    assert "wss://websocket.com" in csp["connect_domains"]


async def test_widget_with_title_and_description():
    """Test widget with custom title and description."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="titled-widget",
        template_uri="ui://widget/titled.html",
        html="<div>Title</div>",
        title="My Custom Title",
        description="Custom description for the widget",
    )
    def titled_widget() -> dict:
        return {}

    # Get the tool
    tools = await app.get_tools()
    tool = tools["titled-widget"]

    assert tool.title == "My Custom Title"
    assert tool.description == "Custom description for the widget"


async def test_widget_with_tags():
    """Test widget with tags."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="tagged-widget",
        template_uri="ui://widget/tagged.html",
        html="<div>Tags</div>",
        tags={"visualization", "data"},
    )
    def tagged_widget() -> dict:
        return {}

    # Get the tool
    tools = await app.get_tools()
    tool = tools["tagged-widget"]

    assert tool.tags == {"visualization", "data"}


async def test_widget_with_enabled_false():
    """Test widget can be disabled."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="disabled-widget",
        template_uri="ui://widget/disabled.html",
        html="<div>Disabled</div>",
        enabled=False,
    )
    def disabled_widget() -> dict:
        return {}

    # Get the tool
    tools = await app.get_tools()
    tool = tools["disabled-widget"]

    assert tool.enabled is False


async def test_widget_with_custom_name():
    """Test widget with custom name different from function name."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="custom-id",
        template_uri="ui://widget/custom.html",
        html="<div>Custom</div>",
    )
    def some_function_name() -> dict:
        return {"test": "data"}

    # Should be registered with custom name
    tools = await app.get_tools()
    assert "custom-id" in tools
    assert "some_function_name" not in tools


async def test_widget_annotations():
    """Test widget has correct default annotations."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="annotated-widget",
        template_uri="ui://widget/annotated.html",
        html="<div>Annotated</div>",
    )
    def annotated_widget() -> dict:
        return {}

    # Get the tool
    tools = await app.get_tools()
    tool = tools["annotated-widget"]

    # Check default widget annotations
    assert tool.annotations is not None
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.readOnlyHint is True


async def test_build_widget_tool_response_helper():
    """Test the build_widget_tool_response helper function."""
    # Text only
    result1 = build_widget_tool_response(response_text="Hello")
    assert result1["content"] == [{"type": "text", "text": "Hello"}]
    assert result1["structuredContent"] == {}

    # Data only
    result2 = build_widget_tool_response(structured_content={"key": "value"})
    assert result2["content"] == []
    assert result2["structuredContent"] == {"key": "value"}

    # Both
    result3 = build_widget_tool_response(
        response_text="Processing...",
        structured_content={"status": "done"}
    )
    assert result3["content"] == [{"type": "text", "text": "Processing..."}]
    assert result3["structuredContent"] == {"status": "done"}


async def test_widget_missing_required_params():
    """Test that widget decorator validates required parameters."""
    app = FastMCP("test")

    with pytest.raises(TypeError, match="missing required keyword argument: 'template_uri'"):
        @app.ui.openai.widget(
            html="<div>Missing URI</div>",
        )
        def bad_widget1() -> dict:
            return {}

    with pytest.raises(TypeError, match="missing required keyword argument: 'html'"):
        @app.ui.openai.widget(
            template_uri="ui://widget/test.html",
        )
        def bad_widget2() -> dict:
            return {}


async def test_widget_invalid_return_type():
    """Test that widget validates return types at runtime."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="bad-return-widget",
        template_uri="ui://widget/bad.html",
        html="<div>Bad</div>",
    )
    def bad_return_widget() -> int:  # Invalid return type
        return 42

    # Calling the tool should raise an error during response transformation
    try:
        await app._tool_manager.call_tool("bad-return-widget", {})
        assert False, "Should have raised TypeError"
    except Exception as e:
        # The error gets wrapped, so check the error message
        assert "must return str, dict, or tuple" in str(e)


async def test_widget_with_exclude_args():
    """Test widget with excluded arguments."""
    app = FastMCP("test")

    @app.ui.openai.widget(
        name="exclude-args-widget",
        template_uri="ui://widget/exclude.html",
        html="<div>Exclude</div>",
        exclude_args=["secret_param"],
    )
    def exclude_args_widget(public_param: str, secret_param: str = "hidden") -> dict:
        return {"public": public_param, "secret": secret_param}

    # Get the tool
    tools = await app.get_tools()
    tool = tools["exclude-args-widget"]

    # Check that secret_param is excluded from schema
    assert "secret_param" not in tool.parameters["properties"]
    assert "public_param" in tool.parameters["properties"]
