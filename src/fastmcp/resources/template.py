"""Resource template functionality."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Annotated, Any
from urllib.parse import unquote

from mcp.types import ResourceTemplate as MCPResourceTemplate
from pydantic import (
    AnyUrl,
    BaseModel,
    BeforeValidator,
    Field,
    TypeAdapter,
    field_validator,
    validate_call,
)

from fastmcp.resources.types import FunctionResource, Resource
from fastmcp.server.dependencies import get_context
from fastmcp.utilities.types import (
    _convert_set_defaults,
    find_kwarg_by_type,
)


def normalize_parameter_name(name: str) -> str:
    """
    Normalize parameter names by replacing special characters with underscores.
    This allows mapping between URI parameter names with special characters
    (e.g., dashes) and valid Python function parameter names.

    Args:
        name: The parameter name to normalize

    Returns:
        A normalized version of the name with special characters replaced with underscores
    """
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def build_regex(template: str) -> tuple[re.Pattern, dict[str, str]]:
    """Build a regex pattern from a URI template, handling special characters in parameter names.

    Returns:
        A tuple containing (regex_pattern, param_name_mapping).
        The param_name_mapping maps regex group names to original parameter names.
    """
    parts = re.split(r"(\{[^}]+\})", template)
    pattern = ""
    param_names = {}  # Map regex group names to original parameter names

    group_counter = 0
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            # Extract the parameter name
            param_name = part[1:-1]
            wildcard = False
            if param_name.endswith("*"):
                param_name = param_name[:-1]
                wildcard = True

            # Use a simple group name that is valid in regex
            group_name = f"p{group_counter}"
            group_counter += 1

            # Store the mapping from group name to original parameter name
            param_names[group_name] = param_name

            # Create the pattern with the safe group name
            if wildcard:
                pattern += f"(?P<{group_name}>.+)"
            else:
                pattern += f"(?P<{group_name}>[^/]+)"
        else:
            pattern += re.escape(part)

    # Return both the regex pattern and the parameter name mappings
    return re.compile(f"^{pattern}$"), param_names


def match_uri_template(
    uri: str, uri_template: str, decode_values: bool = True
) -> dict[str, str] | None:
    """Match a URI against a template and extract parameters, handling special characters.

    Args:
        uri: The URI to match
        uri_template: The template to match against
        decode_values: Whether to URL-decode parameter values (default: True)
    """
    regex, param_names = build_regex(uri_template)
    match = regex.match(uri)
    if match:
        # Map the group names back to the original parameter names
        result = {}
        for group_name, value in match.groupdict().items():
            original_name = param_names[group_name]
            # Decode the value to handle URL-encoded characters if requested
            result[original_name] = unquote(value) if decode_values else value
        return result
    return None


class MyModel(BaseModel):
    key: str
    value: int


class ResourceTemplate(BaseModel):
    """A template for dynamically creating resources."""

    uri_template: str = Field(
        description="URI template with parameters (e.g. weather://{city}/current)"
    )
    name: str = Field(description="Name of the resource")
    description: str | None = Field(description="Description of what the resource does")
    tags: Annotated[set[str], BeforeValidator(_convert_set_defaults)] = Field(
        default_factory=set, description="Tags for the resource"
    )
    mime_type: str = Field(
        default="text/plain", description="MIME type of the resource content"
    )
    fn: Callable[..., Any]
    parameters: dict[str, Any] = Field(
        description="JSON schema for function parameters"
    )

    @field_validator("mime_type", mode="before")
    @classmethod
    def set_default_mime_type(cls, mime_type: str | None) -> str:
        """Set default MIME type if not provided."""
        if mime_type:
            return mime_type
        return "text/plain"

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        uri_template: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        tags: set[str] | None = None,
    ) -> ResourceTemplate:
        """Create a template from a function."""
        from fastmcp.server.context import Context

        func_name = name or fn.__name__
        if func_name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        # Reject functions with *args
        # (**kwargs is allowed because the URI will define the parameter names)
        sig = inspect.signature(fn)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                raise ValueError(
                    "Functions with *args are not supported as resource templates"
                )

        # Auto-detect context parameter if not provided

        context_kwarg = find_kwarg_by_type(fn, kwarg_type=Context)

        # Validate that URI params match function params
        # Use a pattern that extracts parameter names including those with special characters
        uri_params = set(re.findall(r"\{([^{}*]+)(?:\*)?}", uri_template))
        if not uri_params:
            raise ValueError("URI template must contain at least one parameter")

        # Get function parameter names
        func_params = set(sig.parameters.keys())
        if context_kwarg:
            func_params.discard(context_kwarg)

        # Create a mapping between normalized URI params and original URI params
        # This allows matching URI params with dashes to function params with underscores
        uri_param_map = {normalize_parameter_name(p): p for p in uri_params}
        normalized_uri_params = set(uri_param_map.keys())

        # get the parameters that are required
        required_params = {
            p
            for p in func_params
            if sig.parameters[p].default is inspect.Parameter.empty
            and sig.parameters[p].kind != inspect.Parameter.VAR_KEYWORD
            and p != context_kwarg
        }

        # Check if required parameters are a subset of the normalized URI parameters
        if not required_params.issubset(normalized_uri_params):
            # Check for params that don't match when normalized
            missing_params = required_params - normalized_uri_params
            if missing_params:
                raise ValueError(
                    f"Required function arguments {required_params} must be a subset of the URI parameters {uri_params}. "
                    f"Consider renaming function parameters to match URI parameters (with underscores instead of dashes)."
                )

        # Check if the URI parameters are a subset of the function parameters (skip if **kwargs present)
        has_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in sig.parameters.values()
        )

        if not has_kwargs:
            # Check if normalized URI params are a subset of function params
            if not normalized_uri_params.issubset(func_params):
                # Find which params don't have corresponding function params
                missing_func_params = normalized_uri_params - func_params
                orig_missing = {uri_param_map[p] for p in missing_func_params}
                raise ValueError(
                    f"URI parameters {orig_missing} must have corresponding function arguments. "
                    f"Rename your function parameters to match URI parameters (use underscores instead of dashes)."
                )

        # Get schema from TypeAdapter - will fail if function isn't properly typed
        parameters = TypeAdapter(fn).json_schema()

        # ensure the arguments are properly cast
        fn = validate_call(fn)

        return cls(
            uri_template=uri_template,
            name=func_name,
            description=description or fn.__doc__ or "",
            mime_type=mime_type or "text/plain",
            fn=fn,
            parameters=parameters,
            tags=tags or set(),
        )

    def matches(self, uri: str) -> dict[str, Any] | None:
        """Check if URI matches template and extract parameters."""
        return match_uri_template(uri, self.uri_template)

    async def create_resource(self, uri: str, params: dict[str, Any]) -> Resource:
        """Create a resource from the template with the given parameters."""
        from fastmcp.server.context import Context

        try:
            # Add context to parameters if needed
            kwargs = params.copy()
            context_kwarg = find_kwarg_by_type(self.fn, kwarg_type=Context)
            if context_kwarg and context_kwarg not in kwargs:
                kwargs[context_kwarg] = get_context()

            # Convert parameter names with dashes to underscores for function calls
            for key in list(kwargs.keys()):
                normalized_key = normalize_parameter_name(key)
                if (
                    normalized_key != key
                    and normalized_key in inspect.signature(self.fn).parameters
                ):
                    kwargs[normalized_key] = kwargs.pop(key)

            # Call function and check if result is a coroutine
            result = self.fn(**kwargs)
            if inspect.iscoroutine(result):
                result = await result

            return FunctionResource(
                uri=AnyUrl(uri),  # Explicitly convert to AnyUrl
                name=self.name,
                description=self.description,
                mime_type=self.mime_type,
                fn=lambda **kwargs: result,  # Capture result in closure
                tags=self.tags,
            )
        except Exception as e:
            raise ValueError(f"Error creating resource from template: {e}")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResourceTemplate):
            return False
        return self.model_dump() == other.model_dump()

    def to_mcp_template(self, **overrides: Any) -> MCPResourceTemplate:
        """Convert the resource template to an MCPResourceTemplate."""
        kwargs = {
            "uriTemplate": self.uri_template,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }
        return MCPResourceTemplate(**kwargs | overrides)
