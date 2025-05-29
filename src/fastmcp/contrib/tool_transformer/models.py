from copy import deepcopy
from typing import Any, Generic, Literal, Protocol, TypeVar, runtime_checkable

from mcp.types import EmbeddedResource, ImageContent, TextContent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fastmcp.contrib.tool_transformer.errors import (
    ToolParameterAlreadyExistsError,
    ToolParameterNotFoundError,
    ToolParameterOverrideError,
)

T = TypeVar("T", bound=bool | int | float | str)  # | dict[str, Any] | BaseModel)


class ToolParameter(BaseModel, Generic[T]):
    """A base class for a tool parameter."""

    name: str = Field(description="The name of the parameter.")
    description: str | None = Field(
        default=None, description="The description of the parameter."
    )
    required: bool = Field(
        default=False, description="Whether the parameter is required."
    )
    constant: T | None = Field(
        default=None, description="A constant value for the parameter."
    )
    default: T | None = Field(
        default=None, description="A default value for the parameter."
    )

    @model_validator(mode="after")
    def validate_default_and_constant(self):
        if self.default is not None and self.constant is not None:
            msg = "Cannot set both default and constant for a parameter."
            raise ToolParameterOverrideError(msg)

        return self

    @classmethod
    def _get_jsonschema_type(cls) -> str:
        msg = "Subclasses must implement this method."
        raise NotImplementedError(msg)

    def add_into_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Adds the parameter into the schema.

        Args:
            schema: The schema of the tool.

        Returns:
            The updated schema. Does not modify the schema in place.
        """

        working_schema = deepcopy(schema)

        if not working_schema.get("properties"):
            working_schema["properties"] = {}

        if self.name in working_schema["properties"]:
            raise ToolParameterAlreadyExistsError(self.name)

        new_parameter: dict[str, Any] = {
            "type": self._get_jsonschema_type(),
            "title": self.name,
        }

        if self.description is not None:
            new_parameter["description"] = self.description

        if self.default is not None:
            new_parameter["default"] = self.default

        if self.constant is not None:
            new_parameter["const"] = self.constant

        working_schema["properties"][self.name] = new_parameter

        if self.required:
            working_schema.setdefault("required", []).append(self.name)

        return working_schema

    def merge_into_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Merges the parameter into the schema.

        Args:
            schema: The schema of the tool.

        Returns:
            The updated schema. Also modifies the schema in place.
        """
        working_schema = deepcopy(schema)

        if not working_schema.get("properties"):
            working_schema["properties"] = {}

        if self.name not in working_schema["properties"]:
            raise ToolParameterNotFoundError(self.name)

        parameter_schema = working_schema["properties"][self.name]

        if self.description is not None:
            parameter_schema["description"] = self.description

        if self.default is not None:
            parameter_schema["default"] = self.default

        if self.constant is not None:
            parameter_schema["const"] = self.constant

        if self.required and self.name not in working_schema.get("required", []):
            working_schema.setdefault("required", []).append(self.name)

        return working_schema

    def apply_to_schema(
        self,
        schema: dict[str, Any],
        existing_parameter_behavior: Literal["error", "merge"] = "error",
    ) -> dict[str, Any]:
        """
        Applies the parameter to the schema.

        Args:
            schema: The schema of the tool.
            existing_parameter_behavior: The behavior to use when the parameter already exists in the schema.

        """

        already_in_schema = self.name in schema["properties"]

        if not already_in_schema:
            working_schema = self.add_into_schema(schema)
        else:
            if existing_parameter_behavior == "error":
                raise ToolParameterAlreadyExistsError(self.name)
            working_schema = self.merge_into_schema(schema)

        return working_schema


class IntToolParameter(ToolParameter[int]):
    """A parameter that is an integer."""

    @classmethod
    def _get_jsonschema_type(cls) -> str:
        return "number"


class FloatToolParameter(ToolParameter[float]):
    """A parameter that is a float."""

    @classmethod
    def _get_jsonschema_type(cls) -> str:
        return "number"


class StringToolParameter(ToolParameter[str]):
    """A parameter that is a string."""

    @classmethod
    def _get_jsonschema_type(cls) -> str:
        return "string"


class BooleanToolParameter(ToolParameter[bool]):
    """A parameter that is a boolean."""

    @classmethod
    def _get_jsonschema_type(cls) -> str:
        return "boolean"


# class DictToolParameter(ToolParameter[dict[str, Any]]):
#     """A parameter that is an object."""

#     type: dict[str, Any]

#     @classmethod
#     def _get_jsonschema_type(cls) -> str:
#         return "object"


# class BaseModelToolParameter(ToolParameter[BaseModel]):
#     """A parameter that is a model."""

#     type: BaseModel

#     @classmethod
#     def _get_jsonschema_type(cls) -> str:
#         return "object"


ToolParameterTypes = (
    IntToolParameter
    | FloatToolParameter
    | StringToolParameter
    | BooleanToolParameter
    # | DictToolParameter
    # | BaseModelToolParameter
    | ToolParameter
)


@runtime_checkable
class PostToolCallHookProtocol(Protocol):
    async def __call__(
        self,
        response: list[TextContent | ImageContent | EmbeddedResource],
        tool_args: dict[str, Any],
        hook_args: dict[str, Any],
    ) -> None: ...


@runtime_checkable
class PreToolCallHookProtocol(Protocol):
    async def __call__(
        self,
        tool_args: dict[str, Any],
        hook_args: dict[str, Any],
    ) -> None: ...


HookProtocolTypes = PreToolCallHookProtocol | PostToolCallHookProtocol


class ToolOverride(BaseModel):
    """A base class for a tool override that can be used to override a tool."""

    name: str | None = Field(
        default=None, description="The name of the tool to override."
    )
    description: str | None = Field(
        default=None, description="The description of the tool to override."
    )
    parameter_overrides: list[ToolParameterTypes] = Field(
        default_factory=list,
        description="A list of parameter overrides to apply to the tool.",
    )
    hook_parameters: list[ToolParameterTypes] = Field(
        default_factory=list,
        description="A list of hook parameters to apply to the tool.",
    )
    pre_call_hook: PreToolCallHookProtocol | None = Field(
        default=None,
        description="A hook to call before the tool is called.",
        exclude=True,
    )
    post_call_hook: PostToolCallHookProtocol | None = Field(
        default=None,
        description="A hook to call after the tool is called.",
        exclude=True,
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)
