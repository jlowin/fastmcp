import pytest
from mcp.types import EmbeddedResource, TextResourceContents
from pydantic import FileUrl

from fastmcp.prompts.prompt import (
    BaseModel,
    Message,
    Prompt,
    PromptMessage,
    TextContent,
)


class MyTestModel(BaseModel):
    key: str
    value: int


class TestRenderPrompt:
    async def test_basic_fn(self):
        def fn() -> str:
            return "Hello, world!"

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="user", content=TextContent(type="text", text="Hello, world!")
            )
        ]

    async def test_async_fn(self):
        async def fn() -> str:
            return "Hello, world!"

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="user", content=TextContent(type="text", text="Hello, world!")
            )
        ]

    async def test_fn_with_args(self):
        async def fn(name: str, age: int = 30) -> str:
            return f"Hello, {name}! You're {age} years old."

        prompt = Prompt.from_function(fn)
        assert await prompt.render(arguments=dict(name="World")) == [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text", text="Hello, World! You're 30 years old."
                ),
            )
        ]

    async def test_callable_object(self):
        class MyPrompt:
            def __call__(self, name: str) -> str:
                return f"Hello, {name}!"

        prompt = Prompt.from_function(MyPrompt())
        assert await prompt.render(arguments=dict(name="World")) == [
            PromptMessage(
                role="user", content=TextContent(type="text", text="Hello, World!")
            )
        ]

    async def test_async_callable_object(self):
        class MyPrompt:
            async def __call__(self, name: str) -> str:
                return f"Hello, {name}!"

        prompt = Prompt.from_function(MyPrompt())
        assert await prompt.render(arguments=dict(name="World")) == [
            PromptMessage(
                role="user", content=TextContent(type="text", text="Hello, World!")
            )
        ]

    async def test_fn_with_invalid_kwargs(self):
        async def fn(name: str, age: int = 30) -> str:
            return f"Hello, {name}! You're {age} years old."

        prompt = Prompt.from_function(fn)
        with pytest.raises(ValueError):
            await prompt.render(arguments=dict(age=40))

    async def test_fn_returns_message(self):
        async def fn() -> PromptMessage:
            return PromptMessage(
                role="user", content=TextContent(type="text", text="Hello, world!")
            )

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="user", content=TextContent(type="text", text="Hello, world!")
            )
        ]

    async def test_fn_returns_assistant_message(self):
        async def fn() -> PromptMessage:
            return PromptMessage(
                role="assistant", content=TextContent(type="text", text="Hello, world!")
            )

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="assistant", content=TextContent(type="text", text="Hello, world!")
            )
        ]

    async def test_fn_returns_multiple_messages(self):
        expected = [
            Message(role="user", content="Hello, world!"),
            Message(role="assistant", content="How can I help you today?"),
            Message(
                role="user",
                content="I'm looking for a restaurant in the center of town.",
            ),
        ]

        async def fn() -> list[PromptMessage]:
            return expected

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == expected

    async def test_fn_returns_list_of_strings(self):
        expected = [
            "Hello, world!",
            "I'm looking for a restaurant in the center of town.",
        ]

        async def fn() -> list[str]:
            return expected

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(role="user", content=TextContent(type="text", text=t))
            for t in expected
        ]

    async def test_fn_returns_resource_content(self):
        """Test returning a message with resource content."""

        async def fn() -> PromptMessage:
            return PromptMessage(
                role="user",
                content=EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=FileUrl("file://file.txt"),
                        text="File contents",
                        mimeType="text/plain",
                    ),
                ),
            )

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="user",
                content=EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=FileUrl("file://file.txt"),
                        text="File contents",
                        mimeType="text/plain",
                    ),
                ),
            )
        ]

    async def test_fn_returns_mixed_content(self):
        """Test returning messages with mixed content types."""

        async def fn() -> list[PromptMessage | str]:
            return [
                "Please analyze this file:",
                PromptMessage(
                    role="user",
                    content=EmbeddedResource(
                        type="resource",
                        resource=TextResourceContents(
                            uri=FileUrl("file://file.txt"),
                            text="File contents",
                            mimeType="text/plain",
                        ),
                    ),
                ),
                Message(role="assistant", content="I'll help analyze that file."),
            ]

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="user",
                content=TextContent(type="text", text="Please analyze this file:"),
            ),
            PromptMessage(
                role="user",
                content=EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=FileUrl("file://file.txt"),
                        text="File contents",
                        mimeType="text/plain",
                    ),
                ),
            ),
            PromptMessage(
                role="assistant",
                content=TextContent(type="text", text="I'll help analyze that file."),
            ),
        ]

    async def test_fn_returns_message_with_resource(self):
        """Test returning a dict with resource content."""

        async def fn() -> PromptMessage:
            return PromptMessage(
                role="user",
                content=EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=FileUrl("file://file.txt"),
                        text="File contents",
                        mimeType="text/plain",
                    ),
                ),
            )

        prompt = Prompt.from_function(fn)
        assert await prompt.render() == [
            PromptMessage(
                role="user",
                content=EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=FileUrl("file://file.txt"),
                        text="File contents",
                        mimeType="text/plain",
                    ),
                ),
            )
        ]

    async def test_render_with_json_string_list_arg(self):
        """Test that JSON string for a list argument is auto-deserialized."""

        def prompt_with_list(my_list: list[int]) -> str:
            return f"List sum: {sum(my_list)}"

        prompt = Prompt.from_function(prompt_with_list)
        rendered_messages = await prompt.render(arguments={"my_list": "[1, 2, 3, 4]"})
        assert len(rendered_messages) == 1
        assert isinstance(rendered_messages[0].content, TextContent)
        assert rendered_messages[0].content.text == "List sum: 10"

    async def test_render_with_json_string_dict_arg(self):
        """Test that JSON string for a dict argument is auto-deserialized."""

        def prompt_with_dict(my_dict: dict[str, int]) -> str:
            return f"Value for 'b': {my_dict.get('b')}"

        prompt = Prompt.from_function(prompt_with_dict)
        rendered_messages = await prompt.render(
            arguments={"my_dict": '{"a": 1, "b": 2}'}
        )  # escaped JSON string
        assert len(rendered_messages) == 1
        assert isinstance(rendered_messages[0].content, TextContent)
        assert rendered_messages[0].content.text == "Value for 'b': 2"

    async def test_render_with_json_string_basemodel_arg(self):
        """Test that JSON string for a Pydantic BaseModel argument is auto-deserialized."""

        def prompt_with_model(my_model: MyTestModel) -> str:
            return f"Model: {my_model.key}={my_model.value}"

        prompt = Prompt.from_function(prompt_with_model)
        rendered_messages = await prompt.render(
            arguments={"my_model": '{"key": "test", "value": 123}'}
        )  # escaped JSON string
        assert len(rendered_messages) == 1
        assert isinstance(rendered_messages[0].content, TextContent)
        assert rendered_messages[0].content.text == "Model: test=123"

    async def test_render_with_malformed_json_string_arg(self):
        """Test that a malformed JSON string for a list arg is passed as string (and Pydantic errors)."""

        def prompt_with_list(my_list: list[int]) -> str:
            return f"List sum: {sum(my_list)}"

        prompt = Prompt.from_function(prompt_with_list)
        with pytest.raises(
            ValueError, match="Error rendering prompt prompt_with_list."
        ):
            await prompt.render(arguments={"my_list": "not a valid json list"})

    async def test_render_with_non_json_string_for_string_arg(self):
        """Test that a regular string for a string argument is not json.loads-ed."""

        def prompt_with_string(my_string: str) -> str:
            return f"String: {my_string}"

        prompt = Prompt.from_function(prompt_with_string)
        rendered_messages = await prompt.render(arguments={"my_string": '{"a": 1}'})
        assert len(rendered_messages) == 1
        assert isinstance(rendered_messages[0].content, TextContent)
        assert rendered_messages[0].content.text == 'String: {"a": 1}'
