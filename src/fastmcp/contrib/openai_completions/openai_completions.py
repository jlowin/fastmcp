from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from mcp.types import (
    ContentBlock,
    TextContent,
)
from openai import OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared.chat_model import ChatModel
from openai.types.shared_params.function_definition import FunctionDefinition
from pydantic.type_adapter import TypeAdapter
from typing_extensions import override

from fastmcp.tools import Tool
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.completions import (
    BasePendingToolCall,
    CompletionMessageType,
    LLMCompletionsProtocol,
)

MESSAGE_PARAM_TYPE_ADAPTER: TypeAdapter[ChatCompletionMessageParam] = TypeAdapter(
    ChatCompletionMessageParam
)

TOOL_ARGUMENTS_TYPE_ADAPTER: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


class OpenAIPendingToolCall(BasePendingToolCall):
    tool_call_id: str

    @override
    def _tool_result_to_completion_message(
        self, tool_result: ToolResult
    ) -> ChatCompletionToolMessageParam:
        """Convert a tool result to a chat completion tool message."""

        content_parts: list[ChatCompletionContentPartTextParam] = []

        for content_block in tool_result.content:
            match content_block:
                case TextContent():
                    content_parts.append(
                        ChatCompletionContentPartTextParam(
                            type="text", text=content_block.text
                        )
                    )
                case _:
                    msg = "Only TextContent is supported for tool results."
                    raise ValueError(msg)

        return ChatCompletionToolMessageParam(
            role="tool",
            tool_call_id=self.tool_call_id,
            content=content_parts,
        )


class OpenAILLMCompletions(LLMCompletionsProtocol):
    """An implementation of the LLMCompletionsProtocol for OpenAI."""

    def __init__(self, default_model: ChatModel, client: OpenAI | None = None) -> None:
        self.client: OpenAI = client or OpenAI()
        self.default_model: ChatModel = default_model

    @override
    async def text(
        self,
        system_prompt: str,
        messages: Sequence[CompletionMessageType] | CompletionMessageType,
        **kwargs: Any,  # pyright: ignore[reportAny]
    ) -> tuple[CompletionMessageType, ContentBlock]:
        openai_messages = convert_messages_to_openai_messages(system_prompt, messages)

        response: ChatCompletion = self.client.chat.completions.create(
            model=self.default_model,
            messages=openai_messages,
            stream=False,
            **kwargs,  # pyright: ignore[reportAny]
        )

        first_choice = extract_first_choice_completion(response)

        return first_choice.model_dump(), get_content_block_from_completion_message(
            first_choice
        )

    async def _tools(
        self,
        system_prompt: str,
        messages: Sequence[CompletionMessageType] | CompletionMessageType,
        tools: Sequence[Tool] | dict[str, Tool],
        multiple_tool_calls: bool,
        **kwargs: Any,  # pyright: ignore[reportAny]
    ) -> tuple[CompletionMessageType, list[OpenAIPendingToolCall]]:
        openai_messages = convert_messages_to_openai_messages(system_prompt, messages)
        openai_tools = convert_fastmcp_tools_to_openai_tools(tools)

        completion: ChatCompletion = self.client.chat.completions.create(
            model=self.default_model,
            messages=openai_messages,
            parallel_tool_calls=multiple_tool_calls,
            tools=openai_tools,
            tool_choice="required",
            stream=False,
            **kwargs,  # pyright: ignore[reportAny]
        )

        assistant_message = extract_first_choice_completion(completion)

        pending_tool_calls = convert_chat_completion_message_to_pending_tool_calls(
            tools, assistant_message
        )

        return assistant_message.model_dump(), pending_tool_calls

    @override
    async def tool(
        self,
        system_prompt: str,
        messages: Sequence[CompletionMessageType] | CompletionMessageType,
        tools: Sequence[Tool] | dict[str, Tool],
        **kwargs: Any,  # pyright: ignore[reportAny]
    ) -> tuple[CompletionMessageType, OpenAIPendingToolCall]:
        assistant_message, pending_tool_calls = await self._tools(
            system_prompt, messages, tools, False, **kwargs
        )

        return assistant_message, pending_tool_calls[0]

    @override
    async def tools(
        self,
        system_prompt: str,
        messages: Sequence[CompletionMessageType] | CompletionMessageType,
        tools: Sequence[Tool] | dict[str, Tool],
        **kwargs: Any,  # pyright: ignore[reportAny]
    ) -> tuple[CompletionMessageType, list[OpenAIPendingToolCall]]:
        return await self._tools(system_prompt, messages, tools, True, **kwargs)


def extract_first_choice_completion(
    chat_completion: ChatCompletion,
) -> ChatCompletionMessage:
    """Extracts the first choice completion from a ChatCompletion."""
    if len(chat_completion.choices) == 0:
        msg = "No choices to pick from in the chat completion response."
        raise ValueError(msg)

    if len(chat_completion.choices) > 1:
        msg = "Multiple choices to pick from in the chat completion response."
        raise ValueError(msg)

    return chat_completion.choices[0].message


def convert_messages_to_openai_messages(
    system_prompt: str,
    messages: Sequence[CompletionMessageType] | CompletionMessageType,
) -> list[ChatCompletionMessageParam]:
    """Convert messages dictionaries to OpenAI Messages."""

    openai_messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt)
    ]

    for message in messages:
        if isinstance(message, str):
            openai_messages.append(
                ChatCompletionUserMessageParam(role="user", content=message)
            )
        else:
            openai_messages.append(MESSAGE_PARAM_TYPE_ADAPTER.validate_python(message))

    return openai_messages


def convert_chat_completion_message_to_pending_tool_calls(
    tools: Sequence[Tool] | dict[str, Tool],
    chat_completion_message: ChatCompletionMessage,
) -> list[OpenAIPendingToolCall]:
    """Converts the tool calls from a chat completion message to a list of pending tool calls.

    Args:
        tools: The list of tools to use for the tool calls.
        chat_completion_message: The chat completion message to create the pending tool calls from.

    Returns:
        A list of pending tool calls.
    """
    if not (tool_calls := chat_completion_message.tool_calls):
        msg = "No tool_call in the chat completion message."
        raise ValueError(msg)

    if isinstance(tools, dict):
        tools = list(tools.values())

    tools_by_name = {tool.name: tool for tool in tools}

    fastmcp_tool_calls: list[OpenAIPendingToolCall] = []

    for tool_call in tool_calls:
        if not (function_call := tool_call.function):
            msg = "No function call in the tool call."
            raise ValueError(msg)

        if not (tool_name := tool_call.function.name):
            msg = "No name in the function call of the tool call."
            raise ValueError(msg)

        if tool_name not in tools_by_name:
            msg = f"Tool {tool_name} not found in the list of tools."
            raise ValueError(msg)

        tool = tools_by_name[tool_name]

        fastmcp_tool_calls.append(
            OpenAIPendingToolCall(
                tool_call_id=tool_call.id,
                tool=tool,
                arguments=TOOL_ARGUMENTS_TYPE_ADAPTER.validate_json(
                    function_call.arguments
                ),
            )
        )

    return fastmcp_tool_calls


def convert_fastmcp_tools_to_openai_tools(
    fastmcp_tools: Sequence[Tool] | dict[str, Tool],
) -> list[ChatCompletionToolParam]:
    """Create a list of OpenAI Tool Definitions from a list of FastMCP Tools."""
    if isinstance(fastmcp_tools, dict):
        fastmcp_tools = list(fastmcp_tools.values())

    return [convert_fastmcp_tool_to_openai_tool(tool) for tool in fastmcp_tools]


def convert_fastmcp_tool_to_openai_tool(
    fastmcp_tool: Tool,
) -> ChatCompletionToolParam:
    """Create an OpenAI Tool Definition from a FastMCP Tool."""

    tool_name = fastmcp_tool.name
    tool_description = fastmcp_tool.description or ""
    tool_parameters = deepcopy(fastmcp_tool.parameters)

    return ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=tool_name,
            description=tool_description,
            parameters=tool_parameters,
            strict=False,
        ),
    )


def get_content_block_from_completion_message(
    completion_message: ChatCompletionMessage,
) -> ContentBlock:
    """Retrieves an MCP TextContent block from a chat completion."""

    if content := completion_message.content:
        return TextContent(type="text", text=content)
    if refusal := completion_message.refusal:
        return TextContent(type="text", text=refusal)
    msg = "Only Text content is supported."
    raise ValueError(msg)
