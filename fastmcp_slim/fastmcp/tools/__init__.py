from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from .base import InputRequiredToolResult as InputRequiredToolResult
    from .base import Tool as Tool
    from .base import ToolResult as ToolResult
    from .function_tool import FunctionTool as FunctionTool
    from .function_tool import tool as tool
    from .tool_transform import forward as forward
    from .tool_transform import forward_raw as forward_raw

__all__ = [
    "FunctionTool",
    "InputRequiredToolResult",
    "Tool",
    "ToolResult",
    "forward",
    "forward_raw",
    "tool",
]

_LAZY_IMPORTS = {
    "FunctionTool": (".function_tool", "FunctionTool"),
    "InputRequiredToolResult": (".base", "InputRequiredToolResult"),
    "Tool": (".base", "Tool"),
    "ToolResult": (".base", "ToolResult"),
    "forward": (".tool_transform", "forward"),
    "forward_raw": (".tool_transform", "forward_raw"),
    "tool": (".function_tool", "tool"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
