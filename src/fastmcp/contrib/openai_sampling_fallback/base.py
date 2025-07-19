from abc import ABC
from collections.abc import Iterator
from typing import get_args

from mcp.types import ContentBlock, ModelPreferences, SamplingMessage, TextContent
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared.chat_model import ChatModel

from fastmcp.utilities.completions import SamplingProtocol


class BaseOpenAICompatibleSampling(SamplingProtocol, ABC):
    def _iter_models_from_preferences(
        self, model_preferences: ModelPreferences | str | list[str] | None
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

    def _convert_to_openai_messages(
        self, system_prompt: str | None, messages: str | list[str | SamplingMessage]
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

    def _chat_completion_to_mcp_content(
        self, chat_completion: ChatCompletion
    ) -> ContentBlock:
        if len(chat_completion.choices) == 0:
            raise ValueError("No response for completion")

        first_choice = chat_completion.choices[0]

        if content := first_choice.message.content:
            return TextContent(type="text", text=content)

        raise ValueError("No content in response from completion")
