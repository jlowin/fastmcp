"""
Utilities for extracting and managing completion providers from type annotations.
"""

import inspect
from collections.abc import Callable
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from fastmcp.completion.providers import CompletionProvider


def extract_completion_providers(func: Callable) -> dict[str, CompletionProvider]:
    """
    Extract completion providers from function type annotations.

    Scans the function's type annotations for Annotated types that contain
    CompletionProvider instances and returns a mapping of parameter names
    to their completion providers.

    Args:
        func: Function to extract completion providers from

    Returns:
        Dictionary mapping parameter names to CompletionProvider instances

    Example:
        ```python
        def my_func(
            dataset: Annotated[str, Field(description="Dataset"), StaticCompletion(["a", "b"])],
            path: Annotated[str, FilePathCompletion()]
        ) -> str:
            pass

        providers = extract_completion_providers(my_func)
        # Returns: {"dataset": StaticCompletion(["a", "b"]), "path": FilePathCompletion()}
        ```
    """
    providers = {}

    try:
        # Try to get resolved type hints (handles forward references)
        type_hints = get_type_hints(func, include_extras=True)
    except Exception:
        # Fallback to raw annotations if type hint resolution fails
        type_hints = getattr(func, "__annotations__", {})

    for param_name, annotation in type_hints.items():
        # Skip return type annotation
        if param_name == "return":
            continue

        # Check if this is an Annotated type
        if get_origin(annotation) is Annotated:
            args = get_args(annotation)
            if len(args) >= 2:
                # Look for CompletionProvider instances in the annotation metadata
                for metadata in args[1:]:
                    if isinstance(metadata, CompletionProvider):
                        providers[param_name] = metadata
                        break

    return providers


def get_function_signature_with_providers(func: Callable) -> dict[str, Any]:
    """
    Get function signature information including completion providers.

    Args:
        func: Function to analyze

    Returns:
        Dictionary with signature info and completion providers
    """
    sig = inspect.signature(func)
    providers = extract_completion_providers(func)

    return {
        "parameters": {
            name: {
                "annotation": param.annotation,
                "default": param.default if param.default != param.empty else None,
                "has_completion": name in providers,
                "completion_provider": providers.get(name),
            }
            for name, param in sig.parameters.items()
        },
        "completion_providers": providers,
        "return_annotation": sig.return_annotation,
    }
