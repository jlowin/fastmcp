from typing import get_args

from mcp.types import ContentBlock, ModelPreferences, SamplingMessage
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
)
from openai.types.shared.chat_model import ChatModel

from fastmcp.contrib.openai_sampling_fallback.base import (
    BaseOpenAICompatibleSamplingFallback,
)


class OpenAISamplingFallback(BaseOpenAICompatibleSamplingFallback):
    def __init__(self, default_model: ChatModel, client: OpenAI | None = None):
        self.client: OpenAI = client or OpenAI()
        self.default_model: ChatModel = default_model

    async def __call__(
        self,
        messages: str | list[str | SamplingMessage],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_preferences: ModelPreferences | str | list[str] | None = None,
    ) -> ContentBlock:
        openai_messages: list[ChatCompletionMessageParam] = (
            self._convert_to_openai_messages(system_prompt, messages)
        )

        response = self.client.chat.completions.create(
            model=self._select_model_from_preferences(model_preferences),
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return self._chat_completion_to_mcp_content(response)

    def _select_model_from_preferences(
        self, model_preferences: ModelPreferences | str | list[str] | None
    ) -> ChatModel:
        for model_option in self._iter_models_from_preferences(model_preferences):
            if model_option in get_args(ChatModel):
                chosen_model: ChatModel = model_option  # pyright: ignore[reportAssignmentType]
                return chosen_model

        return self.default_model
