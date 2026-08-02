from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from .base import Message as Message
    from .base import Prompt as Prompt
    from .base import PromptArgument as PromptArgument
    from .base import PromptMessage as PromptMessage
    from .base import PromptResult as PromptResult
    from .function_prompt import FunctionPrompt as FunctionPrompt
    from .function_prompt import prompt as prompt

__all__ = [
    "FunctionPrompt",
    "Message",
    "Prompt",
    "PromptArgument",
    "PromptMessage",
    "PromptResult",
    "prompt",
]

_LAZY_IMPORTS = {
    "FunctionPrompt": (".function_prompt", "FunctionPrompt"),
    "Message": (".base", "Message"),
    "Prompt": (".base", "Prompt"),
    "PromptArgument": (".base", "PromptArgument"),
    "PromptMessage": (".base", "PromptMessage"),
    "PromptResult": (".base", "PromptResult"),
    "prompt": (".function_prompt", "prompt"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
