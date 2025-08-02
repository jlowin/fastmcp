from abc import ABC
from collections.abc import Awaitable

from mcp import CreateMessageResult
from mcp.server.session import ServerSession
from mcp.shared.context import LifespanContextT, RequestContext
from mcp.types import CreateMessageRequestParams as SamplingParams
from mcp.types import (
    SamplingMessage,
)


class BaseLLMSamplingHandler(ABC):
    def __call__(
        self,
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: RequestContext[ServerSession, LifespanContextT],
    ) -> str | CreateMessageResult | Awaitable[str | CreateMessageResult]: ...
