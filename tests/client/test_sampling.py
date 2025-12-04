import json
from typing import cast
from unittest.mock import AsyncMock

import pytest
from mcp.types import TextContent, ToolChoice
from pydantic_core import to_json

from fastmcp import Client, Context, FastMCP
from fastmcp.client.sampling import RequestContext, SamplingMessage, SamplingParams
from fastmcp.server.sampling import SamplingTool, sampling_tool
from fastmcp.utilities.types import Image


@pytest.fixture
def fastmcp_server():
    mcp = FastMCP()

    @mcp.tool
    async def simple_sample(message: str, context: Context) -> str:
        result = await context.sample("Hello, world!")
        return result.text  # type: ignore[attr-defined]

    @mcp.tool
    async def sample_with_system_prompt(message: str, context: Context) -> str:
        result = await context.sample("Hello, world!", system_prompt="You love FastMCP")
        return result.text  # type: ignore[attr-defined]

    @mcp.tool
    async def sample_with_messages(message: str, context: Context) -> str:
        result = await context.sample(
            [
                "Hello!",
                SamplingMessage(
                    content=TextContent(
                        type="text", text="How can I assist you today?"
                    ),
                    role="assistant",
                ),
            ]
        )
        return result.text  # type: ignore[attr-defined]

    @mcp.tool
    async def sample_with_image(image_bytes: bytes, context: Context) -> str:
        image = Image(data=image_bytes)

        result = await context.sample(
            [
                SamplingMessage(
                    content=TextContent(type="text", text="What's in this image?"),
                    role="user",
                ),
                SamplingMessage(
                    content=image.to_image_content(),
                    role="user",
                ),
            ]
        )
        return result.text  # type: ignore[attr-defined]

    return mcp


async def test_simple_sampling(fastmcp_server: FastMCP):
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> str:
        return "This is the sample message!"

    async with Client(fastmcp_server, sampling_handler=sampling_handler) as client:
        result = await client.call_tool("simple_sample", {"message": "Hello, world!"})
        assert result.data == "This is the sample message!"


async def test_sampling_with_system_prompt(fastmcp_server: FastMCP):
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> str:
        assert params.systemPrompt is not None
        return params.systemPrompt

    async with Client(fastmcp_server, sampling_handler=sampling_handler) as client:
        result = await client.call_tool(
            "sample_with_system_prompt", {"message": "Hello, world!"}
        )
        assert result.data == "You love FastMCP"


async def test_sampling_with_messages(fastmcp_server: FastMCP):
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> str:
        assert len(messages) == 2

        assert isinstance(messages[0].content, TextContent)
        assert messages[0].content.type == "text"
        assert messages[0].content.text == "Hello!"

        assert isinstance(messages[1].content, TextContent)
        assert messages[1].content.type == "text"
        assert messages[1].content.text == "How can I assist you today?"
        return "I need to think."

    async with Client(fastmcp_server, sampling_handler=sampling_handler) as client:
        result = await client.call_tool(
            "sample_with_messages", {"message": "Hello, world!"}
        )
        assert result.data == "I need to think."


async def test_sampling_with_fallback(fastmcp_server: FastMCP):
    openai_sampling_handler = AsyncMock(return_value="But I need to think")

    fastmcp_server = FastMCP(
        sampling_handler=openai_sampling_handler,
    )

    @fastmcp_server.tool
    async def sample_with_fallback(context: Context) -> str:
        sampling_result = await context.sample("Do not think.")
        return cast(TextContent, sampling_result).text

    client = Client(fastmcp_server)

    async with client:
        call_tool_result = await client.call_tool("sample_with_fallback")

    assert call_tool_result.data == "But I need to think"


async def test_sampling_with_image(fastmcp_server: FastMCP):
    def sampling_handler(
        messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
    ) -> str:
        assert len(messages) == 2
        return to_json(messages).decode()

    async with Client(fastmcp_server, sampling_handler=sampling_handler) as client:
        image_bytes = b"abc123"
        result = await client.call_tool(
            "sample_with_image", {"image_bytes": image_bytes}
        )
        assert json.loads(result.data) == [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": "What's in this image?",
                    "annotations": None,
                    "_meta": None,
                },
                "_meta": None,
            },
            {
                "role": "user",
                "content": {
                    "type": "image",
                    "data": "YWJjMTIz",
                    "mimeType": "image/png",
                    "annotations": None,
                    "_meta": None,
                },
                "_meta": None,
            },
        ]


class TestSamplingWithTools:
    """Tests for sampling with tools functionality."""

    async def test_sampling_with_tools_requires_capability(self):
        """Test that sampling with tools raises error when client lacks capability."""
        from fastmcp.exceptions import ToolError

        mcp = FastMCP()

        @sampling_tool
        def search(query: str) -> str:
            """Search the web."""
            return f"Results for: {query}"

        @mcp.tool
        async def sample_with_tool(context: Context) -> str:
            # This should fail because the client doesn't advertise tools capability
            result = await context.sample(
                messages="Search for Python tutorials",
                tools=[search],
            )
            return str(result)

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> str:
            return "Response"

        async with Client(mcp, sampling_handler=sampling_handler) as client:
            with pytest.raises(ToolError, match="sampling.tools capability"):
                await client.call_tool("sample_with_tool", {})

    async def test_sampling_with_tools_fallback_handler_must_return_correct_type(self):
        """Test that fallback handler must return CreateMessageResultWithTools when tools provided."""
        from fastmcp.exceptions import ToolError

        # This handler returns a string, which is invalid when tools are provided
        invalid_handler = AsyncMock(return_value="Fallback response")

        mcp = FastMCP(sampling_handler=invalid_handler)

        @sampling_tool
        def search(query: str) -> str:
            """Search the web."""
            return f"Results for: {query}"

        @mcp.tool
        async def sample_with_tool(context: Context) -> str:
            result = await context.sample(
                messages="Search for Python tutorials",
                tools=[search],
            )
            return str(result)

        # Client without sampling handler - will use server's fallback
        async with Client(mcp) as client:
            # Handler returns string but tools were provided - should error
            with pytest.raises(
                ToolError, match="must return CreateMessageResultWithTools"
            ):
                await client.call_tool("sample_with_tool", {})

    def test_sampling_tool_schema(self):
        """Test that SamplingTool generates correct schema."""

        @sampling_tool
        def search(query: str, limit: int = 10) -> str:
            """Search the web for results."""
            return f"Results for: {query}"

        assert search.name == "search"
        assert search.description == "Search the web for results."
        assert "query" in search.parameters.get("properties", {})
        assert "limit" in search.parameters.get("properties", {})

    async def test_sampling_tool_run(self):
        """Test that SamplingTool.run() executes correctly."""

        @sampling_tool
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        result = await add.run({"a": 5, "b": 3})
        assert result == 8

    async def test_sampling_tool_run_async(self):
        """Test that SamplingTool.run() works with async functions."""

        @sampling_tool
        async def async_multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        result = await async_multiply.run({"a": 4, "b": 7})
        assert result == 28

    def test_sampling_tool_from_mcp_tool(self):
        """Test creating SamplingTool from FastMCP Tool."""
        from fastmcp.tools.tool import Tool

        def original_fn(x: int, y: int) -> int:
            """Add x and y."""
            return x + y

        mcp_tool = Tool.from_function(original_fn)
        sampling = SamplingTool.from_mcp_tool(mcp_tool)

        assert sampling.name == "original_fn"
        assert sampling.description == "Add x and y."
        assert sampling.fn is mcp_tool.fn

    def test_tool_choice_parameter(self):
        """Test that tool_choice parameter is accepted."""
        # This is a basic type check - full integration requires tools capability

        @sampling_tool
        def search(query: str) -> str:
            """Search."""
            return query

        # Just verify the ToolChoice type works
        choice = ToolChoice(mode="required")
        assert choice.mode == "required"

        choice_auto = ToolChoice(mode="auto")
        assert choice_auto.mode == "auto"

        choice_none = ToolChoice(mode="none")
        assert choice_none.mode == "none"


class TestAutomaticToolLoop:
    """Tests for automatic tool execution loop in ctx.sample()."""

    async def test_automatic_tool_loop_executes_tools(self):
        """Test that ctx.sample() automatically executes tool calls."""
        from mcp.types import CreateMessageResultWithTools, ToolUseContent

        call_count = 0
        tool_was_called = False

        @sampling_tool
        def get_weather(city: str) -> str:
            """Get weather for a city."""
            nonlocal tool_was_called
            tool_was_called = True
            return f"Weather in {city}: sunny, 72°F"

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: return tool use
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_1",
                            name="get_weather",
                            input={"city": "Seattle"},
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )
            else:
                # Second call: return final response
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[TextContent(type="text", text="The weather is sunny!")],
                    model="test-model",
                    stopReason="endTurn",
                )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def weather_assistant(question: str, context: Context) -> str:
            result = await context.sample(
                messages=question,
                tools=[get_weather],
            )
            # Get text from SamplingResult
            return result.text or ""

        async with Client(mcp) as client:
            result = await client.call_tool(
                "weather_assistant", {"question": "What's the weather?"}
            )

        assert tool_was_called
        assert call_count == 2
        assert result.data == "The weather is sunny!"

    async def test_automatic_tool_loop_multiple_tools(self):
        """Test that multiple tool calls in one response are all executed."""
        from mcp.types import CreateMessageResultWithTools, ToolUseContent

        executed_tools: list[str] = []

        @sampling_tool
        def tool_a(x: int) -> int:
            """Tool A."""
            executed_tools.append(f"tool_a({x})")
            return x * 2

        @sampling_tool
        def tool_b(y: int) -> int:
            """Tool B."""
            executed_tools.append(f"tool_b({y})")
            return y + 10

        call_count = 0

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Return multiple tool calls
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use", id="call_a", name="tool_a", input={"x": 5}
                        ),
                        ToolUseContent(
                            type="tool_use", id="call_b", name="tool_b", input={"y": 3}
                        ),
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )
            else:
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[TextContent(type="text", text="Done!")],
                    model="test-model",
                    stopReason="endTurn",
                )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def multi_tool(context: Context) -> str:
            result = await context.sample(messages="Run tools", tools=[tool_a, tool_b])
            return result.text or ""

        async with Client(mcp) as client:
            result = await client.call_tool("multi_tool", {})

        assert executed_tools == ["tool_a(5)", "tool_b(3)"]
        assert result.data == "Done!"

    async def test_automatic_tool_loop_max_iterations(self):
        """Test that max_iterations prevents infinite loops.

        On the last iteration, tool_choice is set to 'none' to force text response.
        """
        from mcp.types import CreateMessageResultWithTools, ToolUseContent

        call_count = 0
        received_tool_choices: list = []

        @sampling_tool
        def looping_tool() -> str:
            """A tool that always gets called again."""
            return "keep going"

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            nonlocal call_count
            call_count += 1
            received_tool_choices.append(params.toolChoice)

            # On last iteration (when tool_choice=none), return text
            if params.toolChoice and params.toolChoice.mode == "none":
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[TextContent(type="text", text="Forced to stop")],
                    model="test-model",
                    stopReason="endTurn",
                )

            # Otherwise keep returning tool use
            return CreateMessageResultWithTools(
                role="assistant",
                content=[
                    ToolUseContent(
                        type="tool_use",
                        id=f"call_{call_count}",
                        name="looping_tool",
                        input={},
                    )
                ],
                model="test-model",
                stopReason="toolUse",
            )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def infinite_loop(context: Context) -> str:
            result = await context.sample(
                messages="Start", tools=[looping_tool], max_iterations=3
            )
            return result.text or "no text"

        async with Client(mcp) as client:
            result = await client.call_tool("infinite_loop", {})

        # Should complete after 3 iterations with forced text response
        assert call_count == 3
        assert result.data == "Forced to stop"
        # Last call should have tool_choice=none
        assert received_tool_choices[-1].mode == "none"

    async def test_automatic_tool_loop_handles_unknown_tool(self):
        """Test that unknown tool names result in error being passed to LLM."""
        from mcp.types import (
            CreateMessageResultWithTools,
            ToolResultContent,
            ToolUseContent,
        )

        @sampling_tool
        def known_tool() -> str:
            """A known tool."""
            return "known result"

        messages_received: list[list[SamplingMessage]] = []

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            messages_received.append(list(messages))

            if len(messages_received) == 1:
                # Request unknown tool
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_1",
                            name="unknown_tool",
                            input={},
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )
            else:
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[TextContent(type="text", text="Handled error")],
                    model="test-model",
                    stopReason="endTurn",
                )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def test_unknown(context: Context) -> str:
            result = await context.sample(messages="Test", tools=[known_tool])
            return result.text or ""

        async with Client(mcp) as client:
            result = await client.call_tool("test_unknown", {})

        # Check that error was passed back in messages
        assert len(messages_received) == 2
        last_messages = messages_received[1]
        # Find the tool result message
        tool_result_msg = None
        for msg in last_messages:
            if isinstance(msg.content, ToolResultContent):
                tool_result_msg = msg
                break
        assert tool_result_msg is not None
        assert tool_result_msg.content.isError is True  # type: ignore[union-attr]
        # Content is list of TextContent objects
        error_text = tool_result_msg.content.content[0].text  # type: ignore[union-attr]
        assert "Unknown tool" in error_text
        assert result.data == "Handled error"

    async def test_automatic_tool_loop_handles_tool_exception(self):
        """Test that tool exceptions are caught and passed to LLM as errors."""
        from mcp.types import (
            CreateMessageResultWithTools,
            ToolResultContent,
            ToolUseContent,
        )

        @sampling_tool
        def failing_tool() -> str:
            """A tool that raises an exception."""
            raise ValueError("Tool failed intentionally")

        messages_received: list[list[SamplingMessage]] = []

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            messages_received.append(list(messages))

            if len(messages_received) == 1:
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_1",
                            name="failing_tool",
                            input={},
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )
            else:
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[TextContent(type="text", text="Handled error")],
                    model="test-model",
                    stopReason="endTurn",
                )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def test_exception(context: Context) -> str:
            result = await context.sample(messages="Test", tools=[failing_tool])
            return result.text or ""

        async with Client(mcp) as client:
            result = await client.call_tool("test_exception", {})

        # Check that error was passed back
        assert len(messages_received) == 2
        last_messages = messages_received[1]
        tool_result_msg = None
        for msg in last_messages:
            if isinstance(msg.content, ToolResultContent):
                tool_result_msg = msg
                break
        assert tool_result_msg is not None
        assert tool_result_msg.content.isError is True  # type: ignore[union-attr]
        # Content is list of TextContent objects
        error_text = tool_result_msg.content.content[0].text  # type: ignore[union-attr]
        assert "Tool failed intentionally" in error_text
        assert result.data == "Handled error"

    async def test_max_iterations_one_for_manual_loop(self):
        """Test that max_iterations=1 forces text on first call for manual loop building.

        With max_iterations=1, tool_choice is set to 'none' on the first (and only) call,
        forcing a text response so users can build their own loop using history.
        """
        from mcp.types import CreateMessageResultWithTools, ToolUseContent

        received_tool_choices: list = []

        @sampling_tool
        def my_tool() -> str:
            """A tool."""
            return "result"

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            received_tool_choices.append(params.toolChoice)

            # With tool_choice=none, return text response
            if params.toolChoice and params.toolChoice.mode == "none":
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[TextContent(type="text", text="Forced text response")],
                    model="test-model",
                    stopReason="endTurn",
                )

            # Otherwise return tool use (shouldn't happen with max_iterations=1)
            return CreateMessageResultWithTools(
                role="assistant",
                content=[
                    ToolUseContent(
                        type="tool_use", id="call_1", name="my_tool", input={}
                    )
                ],
                model="test-model",
                stopReason="toolUse",
            )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def single_iteration(context: Context) -> str:
            result = await context.sample(
                messages="Test", tools=[my_tool], max_iterations=1
            )
            return result.text or "no text"

        async with Client(mcp) as client:
            result = await client.call_tool("single_iteration", {})

        # Should get forced text response
        assert result.data == "Forced text response"
        # First and only call should have tool_choice=none
        assert len(received_tool_choices) == 1
        assert received_tool_choices[0].mode == "none"


class TestSamplingResultType:
    """Tests for result_type parameter (structured output)."""

    async def test_result_type_creates_final_response_tool(self):
        """Test that result_type creates a synthetic final_response tool."""
        from mcp.types import CreateMessageResultWithTools, ToolUseContent
        from pydantic import BaseModel

        class MathResult(BaseModel):
            answer: int
            explanation: str

        received_tools: list = []

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            received_tools.extend(params.tools or [])

            # Return the final_response tool call
            return CreateMessageResultWithTools(
                role="assistant",
                content=[
                    ToolUseContent(
                        type="tool_use",
                        id="call_1",
                        name="final_response",
                        input={"answer": 42, "explanation": "The meaning of life"},
                    )
                ],
                model="test-model",
                stopReason="toolUse",
            )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def math_tool(context: Context) -> str:
            result = await context.sample(
                messages="What is 6 * 7?",
                result_type=MathResult,
            )
            # result.result should be a MathResult object
            return f"{result.result.answer}: {result.result.explanation}"  # type: ignore[attr-defined]

        async with Client(mcp) as client:
            result = await client.call_tool("math_tool", {})

        # Check that final_response tool was added
        tool_names = [t.name for t in received_tools]
        assert "final_response" in tool_names

        # Check the result
        assert result.data == "42: The meaning of life"

    async def test_result_type_with_user_tools(self):
        """Test result_type works alongside user-provided tools."""
        from mcp.types import CreateMessageResultWithTools, ToolUseContent
        from pydantic import BaseModel

        class SearchResult(BaseModel):
            summary: str
            sources: list[str]

        @sampling_tool
        def search(query: str) -> str:
            """Search for information."""
            return f"Found info about: {query}"

        call_count = 0
        tool_was_called = False

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            nonlocal call_count, tool_was_called
            call_count += 1

            if call_count == 1:
                # First call: use the search tool
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_1",
                            name="search",
                            input={"query": "Python tutorials"},
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )
            else:
                # Second call: call final_response
                tool_was_called = True
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_2",
                            name="final_response",
                            input={
                                "summary": "Python is great",
                                "sources": ["python.org", "docs.python.org"],
                            },
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def research(context: Context) -> str:
            result = await context.sample(
                messages="Research Python",
                tools=[search],
                result_type=SearchResult,
            )
            return f"{result.result.summary} - {len(result.result.sources)} sources"  # type: ignore[attr-defined]

        async with Client(mcp) as client:
            result = await client.call_tool("research", {})

        assert tool_was_called
        assert result.data == "Python is great - 2 sources"

    async def test_result_type_validation_error_retries(self):
        """Test that validation errors are sent back to LLM for retry."""
        from mcp.types import (
            CreateMessageResultWithTools,
            ToolResultContent,
            ToolUseContent,
        )
        from pydantic import BaseModel

        class StrictResult(BaseModel):
            value: int  # Must be an int

        messages_received: list[list[SamplingMessage]] = []

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            messages_received.append(list(messages))

            if len(messages_received) == 1:
                # First call: invalid type
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_1",
                            name="final_response",
                            input={"value": "not_an_int"},  # Wrong type
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )
            else:
                # Second call: valid type after seeing error
                return CreateMessageResultWithTools(
                    role="assistant",
                    content=[
                        ToolUseContent(
                            type="tool_use",
                            id="call_2",
                            name="final_response",
                            input={"value": 42},  # Correct type
                        )
                    ],
                    model="test-model",
                    stopReason="toolUse",
                )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def validate_tool(context: Context) -> str:
            result = await context.sample(
                messages="Give me a number",
                result_type=StrictResult,
            )
            return str(result.result.value)  # type: ignore[attr-defined]

        async with Client(mcp) as client:
            result = await client.call_tool("validate_tool", {})

        # Should have retried after validation error
        assert len(messages_received) == 2

        # Check that error was passed back
        last_messages = messages_received[1]
        tool_result_msg = None
        for msg in last_messages:
            if isinstance(msg.content, ToolResultContent):
                tool_result_msg = msg
                break
        assert tool_result_msg is not None
        assert tool_result_msg.content.isError is True  # type: ignore[union-attr]
        error_text = tool_result_msg.content.content[0].text  # type: ignore[union-attr]
        assert "Validation error" in error_text

        # Final result should be correct
        assert result.data == "42"

    async def test_sampling_result_has_text_and_history(self):
        """Test that SamplingResult has text, result, and history attributes."""
        from mcp.types import CreateMessageResultWithTools

        def sampling_handler(
            messages: list[SamplingMessage], params: SamplingParams, ctx: RequestContext
        ) -> CreateMessageResultWithTools:
            return CreateMessageResultWithTools(
                role="assistant",
                content=[TextContent(type="text", text="Hello world")],
                model="test-model",
                stopReason="endTurn",
            )

        mcp = FastMCP(sampling_handler=sampling_handler)

        @mcp.tool
        async def check_result(context: Context) -> str:
            result = await context.sample(messages="Say hello")
            # Check all attributes exist
            assert result.text == "Hello world"
            assert result.result == "Hello world"
            assert len(result.history) >= 1
            return "ok"

        async with Client(mcp) as client:
            result = await client.call_tool("check_result", {})

        assert result.data == "ok"
