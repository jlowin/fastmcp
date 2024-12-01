import fastmcp
from fastmcp.exceptions import ToolError

from fastmcp.utilities.func_metadata import func_metadata, FuncMetadata
from pydantic import BaseModel, Field


import inspect
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from fastmcp.server import Context


class Tool(BaseModel):
    """Internal tool registration info."""

    fn: Callable = Field(exclude=True)
    name: str = Field(description="Name of the tool")
    description: str = Field(description="Description of what the tool does")
    parameters: dict = Field(description="JSON schema for tool parameters")
    fn_metadata: FuncMetadata = Field(
        description="Metadata about the function including a pydantic model for tool arguments"
    )
    is_async: bool = Field(description="Whether the tool is async")
    context_kwarg: Optional[str] = Field(
        None, description="Name of the kwarg that should receive context"
    )

    @classmethod
    def from_function(
        cls,
        fn: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        context_kwarg: Optional[str] = None,
    ) -> "Tool":
        """Create a Tool from a function."""
        func_name = name or fn.__name__

        if func_name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        func_doc = description or fn.__doc__ or ""
        is_async = inspect.iscoroutinefunction(fn)

        # Find context parameter if it exists
        if context_kwarg is None:
            sig = inspect.signature(fn)
            for param_name, param in sig.parameters.items():
                if param.annotation is fastmcp.Context:
                    context_kwarg = param_name
                    break

        func_arg_metadata = func_metadata(
            fn,
            skip_names=[context_kwarg] if context_kwarg is not None else [],
        )
        parameters = func_arg_metadata.arg_model.model_json_schema()

        return cls(
            fn=fn,
            name=func_name,
            description=func_doc,
            parameters=parameters,
            fn_metadata=func_arg_metadata,
            is_async=is_async,
            context_kwarg=context_kwarg,
        )

    async def run(self, arguments: dict, context: Optional["Context"] = None) -> Any:
        """Run the tool with arguments."""
        try:
            return await self.fn_metadata.call_fn_with_arg_validation(
                self.fn,
                self.is_async,
                arguments,
                {self.context_kwarg: context}
                if self.context_kwarg is not None
                else None,
            )
        except Exception as e:
            raise ToolError(f"Error executing tool {self.name}: {e}") from e
