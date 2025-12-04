import json
from collections.abc import Iterator, Sequence
from typing import Any, get_args

from mcp import ClientSession, ServerSession
from mcp.shared.context import LifespanContextT, RequestContext
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    CreateMessageResult,
    CreateMessageResultWithTools,
    ModelPreferences,
    SamplingMessage,
    StopReason,
    TextContent,
    Tool,
    ToolChoice,
    ToolUseContent,
)

try:
    from openai import NOT_GIVEN, NotGiven, OpenAI
    from openai.types.chat import (
        ChatCompletion,
        ChatCompletionAssistantMessageParam,
        ChatCompletionMessageParam,
        ChatCompletionSystemMessageParam,
        ChatCompletionToolChoiceOptionParam,
        ChatCompletionToolParam,
        ChatCompletionUserMessageParam,
    )
    from openai.types.shared.chat_model import ChatModel
    from openai.types.shared_params import FunctionDefinition
except ImportError as e:
    raise ImportError(
        "The `openai` package is not installed. Please install `fastmcp[openai]` or add `openai` to your dependencies manually."
    ) from e

from typing_extensions import override

from fastmcp.experimental.sampling.handlers.base import BaseLLMSamplingHandler


class OpenAISamplingHandler(BaseLLMSamplingHandler):
    def __init__(self, default_model: ChatModel, client: OpenAI | None = None):
        self.client: OpenAI = client or OpenAI()
        self.default_model: ChatModel = default_model

    @override
    async def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: RequestContext[ServerSession, LifespanContextT]
        | RequestContext[ClientSession, LifespanContextT],
    ) -> CreateMessageResult | CreateMessageResultWithTools:
        openai_messages: list[ChatCompletionMessageParam] = (
            self._convert_to_openai_messages(
                system_prompt=params.systemPrompt,
                messages=messages,
            )
        )

        model: ChatModel = self._select_model_from_preferences(params.modelPreferences)

        # Convert MCP tools to OpenAI format
        openai_tools: list[ChatCompletionToolParam] | NotGiven = NOT_GIVEN
        if params.tools:
            openai_tools = self._convert_tools_to_openai(params.tools)

        # Convert tool_choice to OpenAI format
        openai_tool_choice: ChatCompletionToolChoiceOptionParam | NotGiven = NOT_GIVEN
        if params.toolChoice:
            openai_tool_choice = self._convert_tool_choice_to_openai(params.toolChoice)

        response = self.client.chat.completions.create(
            model=model,
            messages=openai_messages,
            temperature=params.temperature or NOT_GIVEN,
            max_tokens=params.maxTokens,
            stop=params.stopSequences or NOT_GIVEN,
            tools=openai_tools,
            tool_choice=openai_tool_choice,
        )

        # Return appropriate result type based on whether tools were provided
        if params.tools:
            return self._chat_completion_to_result_with_tools(response)
        return self._chat_completion_to_create_message_result(response)

    @staticmethod
    def _iter_models_from_preferences(
        model_preferences: ModelPreferences | str | list[str] | None,
    ) -> Iterator[str]:
        if model_preferences is None:
            return

        if isinstance(model_preferences, str) and model_preferences in get_args(
            ChatModel
        ):
            yield model_preferences

        if isinstance(model_preferences, list):
            yield from model_preferences

        if isinstance(model_preferences, ModelPreferences):
            if not (hints := model_preferences.hints):
                return

            for hint in hints:
                if not (name := hint.name):
                    continue

                yield name

    @staticmethod
    def _convert_to_openai_messages(
        system_prompt: str | None, messages: Sequence[SamplingMessage]
    ) -> list[ChatCompletionMessageParam]:
        openai_messages: list[ChatCompletionMessageParam] = []

        if system_prompt:
            openai_messages.append(
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=system_prompt,
                )
            )

        if isinstance(messages, str):
            openai_messages.append(
                ChatCompletionUserMessageParam(
                    role="user",
                    content=messages,
                )
            )

        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, str):
                    openai_messages.append(
                        ChatCompletionUserMessageParam(
                            role="user",
                            content=message,
                        )
                    )
                    continue

                if not isinstance(message.content, TextContent):
                    raise ValueError("Only text content is supported")

                if message.role == "user":
                    openai_messages.append(
                        ChatCompletionUserMessageParam(
                            role="user",
                            content=message.content.text,
                        )
                    )
                else:
                    openai_messages.append(
                        ChatCompletionAssistantMessageParam(
                            role="assistant",
                            content=message.content.text,
                        )
                    )

        return openai_messages

    @staticmethod
    def _chat_completion_to_create_message_result(
        chat_completion: ChatCompletion,
    ) -> CreateMessageResult:
        if len(chat_completion.choices) == 0:
            raise ValueError("No response for completion")

        first_choice = chat_completion.choices[0]

        if content := first_choice.message.content:
            return CreateMessageResult(
                content=TextContent(type="text", text=content),
                role="assistant",
                model=chat_completion.model,
            )

        raise ValueError("No content in response from completion")

    def _select_model_from_preferences(
        self, model_preferences: ModelPreferences | str | list[str] | None
    ) -> ChatModel:
        for model_option in self._iter_models_from_preferences(model_preferences):
            if model_option in get_args(ChatModel):
                chosen_model: ChatModel = model_option  # pyright: ignore[reportAssignmentType]
                return chosen_model

        return self.default_model

    @staticmethod
    def _convert_tools_to_openai(tools: list[Tool]) -> list[ChatCompletionToolParam]:
        """Convert MCP tools to OpenAI tool format."""
        openai_tools: list[ChatCompletionToolParam] = []
        for tool in tools:
            # Build parameters dict, ensuring required fields
            parameters: dict[str, Any] = dict(tool.inputSchema)
            if "type" not in parameters:
                parameters["type"] = "object"

            openai_tools.append(
                ChatCompletionToolParam(
                    type="function",
                    function=FunctionDefinition(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=parameters,
                    ),
                )
            )
        return openai_tools

    @staticmethod
    def _convert_tool_choice_to_openai(
        tool_choice: ToolChoice,
    ) -> ChatCompletionToolChoiceOptionParam:
        """Convert MCP tool_choice to OpenAI format."""
        if tool_choice.mode == "auto":
            return "auto"
        elif tool_choice.mode == "required":
            return "required"
        elif tool_choice.mode == "none":
            return "none"
        else:
            # Unknown mode, default to auto
            return "auto"

    @staticmethod
    def _chat_completion_to_result_with_tools(
        chat_completion: ChatCompletion,
    ) -> CreateMessageResultWithTools:
        """Convert OpenAI response to CreateMessageResultWithTools."""
        if len(chat_completion.choices) == 0:
            raise ValueError("No response for completion")

        first_choice = chat_completion.choices[0]
        message = first_choice.message

        # Determine stop reason
        stop_reason: StopReason
        if first_choice.finish_reason == "tool_calls":
            stop_reason = "toolUse"
        elif first_choice.finish_reason == "stop":
            stop_reason = "endTurn"
        elif first_choice.finish_reason == "length":
            stop_reason = "maxTokens"
        else:
            stop_reason = "endTurn"

        # Build content list
        content: list[TextContent | ToolUseContent] = []

        # Add text content if present
        if message.content:
            content.append(TextContent(type="text", text=message.content))

        # Add tool calls if present
        if message.tool_calls:
            for tool_call in message.tool_calls:
                # Parse the arguments JSON string
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                content.append(
                    ToolUseContent(
                        type="tool_use",
                        id=tool_call.id,
                        name=tool_call.function.name,
                        input=arguments,
                    )
                )

        # Must have at least some content
        if not content:
            raise ValueError("No content in response from completion")

        return CreateMessageResultWithTools(
            content=content,
            role="assistant",
            model=chat_completion.model,
            stopReason=stop_reason,
        )
