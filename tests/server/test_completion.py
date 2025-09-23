"""
Tests for type annotation-based completion system.
"""

from typing import Annotated, Literal

import pytest
from mcp.types import CompletionArgument, PromptReference
from pydantic import Field

from fastmcp import FastMCP
from fastmcp.completion import (
    DynamicCompletion,
    FuzzyCompletion,
    StaticCompletion,
    extract_completion_providers,
)


class TestCompletionProviders:
    """Test completion provider implementations."""

    @pytest.mark.asyncio
    async def test_static_completion(self):
        """Test StaticCompletion provider."""
        provider = StaticCompletion(["apple", "banana", "cherry"])

        # Test empty partial returns all choices
        result = await provider.complete("")
        assert result == ["apple", "banana", "cherry"]

        # Test partial matching
        result = await provider.complete("a")
        assert result == ["apple"]

        result = await provider.complete("b")
        assert result == ["banana"]

        # Test case insensitive matching
        result = await provider.complete("A")
        assert result == ["apple"]

        # Test no matches
        result = await provider.complete("xyz")
        assert result == []

    @pytest.mark.asyncio
    async def test_fuzzy_completion(self):
        """Test FuzzyCompletion provider."""
        provider = FuzzyCompletion(["customer_data", "sales_records", "user_activity"])

        # Test empty partial returns all choices
        result = await provider.complete("")
        assert result == []

        # Test fuzzy matching (substring anywhere)
        result = await provider.complete("data")
        assert result == ["customer_data"]

        result = await provider.complete("record")
        assert result == ["sales_records"]

        # Test case insensitive fuzzy matching
        result = await provider.complete("USER")
        assert result == ["user_activity"]

        # Test partial word matching
        result = await provider.complete("sale")
        assert result == ["sales_records"]


class TestCompletionExtraction:
    """Test extraction of completion providers from type annotations."""

    def test_extract_completion_providers(self):
        """Test extraction from function with annotated parameters."""

        def sample_function(
            dataset: Annotated[
                str, Field(description="Dataset name"), StaticCompletion(["a", "b"])
            ],
            analysis: Annotated[str, FuzzyCompletion(["x", "y"])],
            format: Annotated[
                Literal["json", "csv"], Field(description="Output format")
            ],
            regular_param: str,
        ) -> str:
            return f"Processing {dataset}"

        providers = extract_completion_providers(sample_function)

        # Should extract providers for annotated parameters only
        assert len(providers) == 2
        assert "dataset" in providers
        assert "analysis" in providers
        assert "format" not in providers  # Literal without completion provider
        assert "regular_param" not in providers  # No annotation

        # Verify provider types
        assert isinstance(providers["dataset"], StaticCompletion)
        assert isinstance(providers["analysis"], FuzzyCompletion)

    def test_extract_no_completion_providers(self):
        """Test extraction from function with no completion providers."""

        def sample_function(param1: str, param2: int) -> str:
            return "test"

        providers = extract_completion_providers(sample_function)
        assert providers == {}

    def test_extract_mixed_annotations(self):
        """Test extraction with mixed annotation types."""

        def sample_function(
            with_completion: Annotated[
                str, Field(description="Has completion"), StaticCompletion(["test"])
            ],
            with_field_only: Annotated[str, Field(description="Field only")],
            regular_param: str,
        ) -> str:
            return "test"

        providers = extract_completion_providers(sample_function)

        assert len(providers) == 1
        assert "with_completion" in providers
        assert "with_field_only" not in providers
        assert "regular_param" not in providers


class TestFastMCPIntegration:
    """Test integration with FastMCP server."""

    @pytest.mark.asyncio
    async def test_prompt_completion_extraction(self):
        """Test that prompt decorators extract completion providers."""
        server = FastMCP("Test Server")

        @server.prompt
        async def process_file(
            operation: Annotated[str, StaticCompletion(["read", "write", "delete"])],
        ) -> str:
            return f"Processing {operation}"

        # Verify completion providers were extracted and stored
        prompt_key = process_file.key
        assert prompt_key in server._completion_providers

        providers = server._completion_providers[prompt_key]
        assert "operation" in providers

        assert isinstance(providers["operation"], StaticCompletion)

    @pytest.mark.asyncio
    async def test_completion_request_handling(self):
        """Test that completion requests use type annotation providers."""
        server = FastMCP("Test Server")

        @server.prompt
        async def test_prompt(
            category: Annotated[str, StaticCompletion(["docs", "emails", "code"])],
        ) -> str:
            return f"Category: {category}"

        # Create completion request
        ref = PromptReference(type="ref/prompt", name="test_prompt")
        argument = CompletionArgument(name="category", value="d")

        # Execute completion
        result = await server._completion(ref, argument)

        # Should get completion from type annotation provider
        assert result.completion.values == ["docs"]
        assert result.completion.total == 1
        assert not result.completion.hasMore

    @pytest.mark.asyncio
    async def test_completion_mounting(self):
        """Test that completion providers work with server mounting."""
        child_server = FastMCP("Child Server")
        parent_server = FastMCP("Parent Server")

        @child_server.prompt
        async def child_prompt(
            dataset: Annotated[str, StaticCompletion(["child_data1", "child_data2"])],
        ) -> str:
            return f"Child processing {dataset}"

        # Mount child server with prefix
        parent_server.mount(child_server, prefix="child")

        # Verify completion providers are mounted with correct prefix
        prefixed_key = "child_child_prompt"  # prefix + _ + original key
        assert prefixed_key in parent_server._completion_providers

        providers = parent_server._completion_providers[prefixed_key]
        assert "dataset" in providers
        assert isinstance(providers["dataset"], StaticCompletion)

    @pytest.mark.asyncio
    async def test_completion_import(self):
        """Test that completion providers work with server import."""
        source_server = FastMCP("Source Server")
        target_server = FastMCP("Target Server")

        @source_server.prompt
        async def source_prompt(
            type: Annotated[str, StaticCompletion(["source1", "source2"])],
        ) -> str:
            return f"Source: {type}"

        # Import source server with prefix
        await target_server.import_server(source_server, prefix="imported")

        # Verify completion providers are imported with correct prefix
        prefixed_key = "imported_source_prompt"
        assert prefixed_key in target_server._completion_providers

        providers = target_server._completion_providers[prefixed_key]
        assert "type" in providers
        assert isinstance(providers["type"], StaticCompletion)


@pytest.mark.asyncio
async def test_completion_provider_error_handling():
    """Test error handling in completion providers."""
    server = FastMCP("Test Server")

    async def failing_completion(partial: str) -> list[str]:
        raise ValueError("Completion failed")

    @server.prompt
    async def test_prompt(
        param: Annotated[str, DynamicCompletion(failing_completion)],
    ) -> str:
        return f"Result: {param}"

    # Create completion request
    ref = PromptReference(
        type="ref/prompt", name="test_prompt"
    )  # Note: This would be prompt ref in real usage
    argument = CompletionArgument(name="param", value="test")

    # Should handle error gracefully and return empty completion
    result = await server._completion(ref, argument)

    assert result.completion.values == []
    assert result.completion.total == 0
    assert not result.completion.hasMore
