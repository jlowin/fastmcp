"""Base classes for FastMCP prompts."""

import json
from typing import Any, Callable, Dict, Literal, Optional, Sequence, Union
import inspect

from pydantic import BaseModel, Field, TypeAdapter, field_validator, validate_call
from mcp.types import TextContent, ImageContent, EmbeddedResource
import pydantic_core


class Message(BaseModel):
    """Base class for all prompt messages."""

    role: Literal["user", "assistant"]
    content: Union[TextContent, ImageContent, EmbeddedResource]

    def __init__(
        self, content: Union[TextContent, ImageContent, EmbeddedResource], **kwargs: Any
    ):
        super().__init__(content=content, **kwargs)

    @field_validator("content", mode="before")
    def validate_content(cls, v: Any) -> Any:
        if isinstance(v, str):
            return TextContent(type="text", text=v)
        return v


class UserMessage(Message):
    """A message from the user."""

    role: Literal["user"] = "user"


class AssistantMessage(Message):
    """A message from the assistant."""

    role: Literal["assistant"] = "assistant"


message_validator: TypeAdapter[UserMessage | AssistantMessage] = TypeAdapter(
    Union[UserMessage, AssistantMessage]
)


class PromptArgument(BaseModel):
    """An argument that can be passed to a prompt."""

    name: str = Field(description="Name of the argument")
    description: str | None = Field(
        None, description="Description of what the argument does"
    )
    required: bool = Field(
        default=False, description="Whether the argument is required"
    )


class Prompt(BaseModel):
    """A prompt template that can be rendered with parameters."""

    name: str = Field(description="Name of the prompt")
    description: str | None = Field(
        None, description="Description of what the prompt does"
    )
    arguments: list[PromptArgument] | None = Field(
        None, description="Arguments that can be passed to the prompt"
    )
    fn: Callable = Field(exclude=True)

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Sequence[Message]],
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> "Prompt":
        """Create a Prompt from a function."""
        func_name = name or fn.__name__

        if func_name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        # Get schema from TypeAdapter - will fail if function isn't properly typed
        parameters = TypeAdapter(fn).json_schema()

        # Convert parameters to PromptArguments
        arguments = []
        if "properties" in parameters:
            for param_name, param in parameters["properties"].items():
                required = param_name in parameters.get("required", [])
                arguments.append(
                    PromptArgument(
                        name=param_name,
                        description=param.get("description"),
                        required=required,
                    )
                )

        # ensure the arguments are properly cast
        fn = validate_call(fn)

        return cls(
            name=func_name,
            description=description or fn.__doc__ or "",
            arguments=arguments,
            fn=fn,
        )

    async def render(self, arguments: Optional[Dict[str, Any]] = None) -> list[Message]:
        """Render the prompt with arguments."""
        # Validate required arguments
        if self.arguments:
            required = {arg.name for arg in self.arguments if arg.required}
            provided = set(arguments or {})
            missing = required - provided
            if missing:
                raise ValueError(f"Missing required arguments: {missing}")

        try:
            # Call function and check if result is a coroutine
            result = self.fn(**(arguments or {}))
            if inspect.iscoroutine(result):
                result = await result

            # Validate messages
            if not isinstance(result, (list, tuple)):
                result = [result]

            # Convert result to messages
            messages = []
            for msg in result:
                try:
                    if isinstance(msg, Message):
                        messages.append(msg)
                    elif isinstance(msg, dict):
                        msg = message_validator.validate_python(msg)
                        messages.append(msg)
                    elif isinstance(msg, str):
                        messages.append(
                            UserMessage(content=TextContent(type="text", text=msg))
                        )
                    else:
                        msg = json.dumps(pydantic_core.to_jsonable_python(msg))
                        messages.append(Message(role="user", content=msg))
                except Exception:
                    raise ValueError(
                        f"Could not convert prompt result to message: {msg}"
                    )

            return messages
        except Exception as e:
            raise ValueError(f"Error rendering prompt {self.name}: {e}")
