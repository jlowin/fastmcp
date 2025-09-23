"""
FastMCP-specific completion system for Prompts and Resources.

This module provides completion providers that suggest actual FastMCP components
(prompts, resources, resource templates) rather than generic string completions.
"""

from fastmcp.completion.providers import (
    CompletionProvider,
    PromptCompletion,
    ResourceCompletion,
    ResourceTemplateCompletion,
    StaticCompletion,
)
from fastmcp.completion.utils import extract_completion_providers

__all__ = [
    "CompletionProvider",
    "PromptCompletion",
    "ResourceCompletion",
    "ResourceTemplateCompletion",
    "StaticCompletion",
    "extract_completion_providers",
]
