# Makefile for common project tasks

.PHONY: install deps test lint format docs test-resource-templates test-sse-bug test-resource-template-fix

install:
	@echo "Installing all dependencies via uv..."
	uv sync --all-extras --all-groups --frozen
	uv run pre-commit install

test: 
	@echo "Running tests..."
	uv run pytest tests

test-resource-templates:
	@echo "Running resource template tests with special characters in parameters..."
	uv run pytest tests/resources/test_resource_template_special_chars.py -v

test-resource-template-fix:
	@echo "Running resource template fix tests..."
	uv run pytest tests/resources/test_resource_template_fix.py tests/resources/test_resource_template_special_chars.py -v

test-sse-bug:
	@echo "Running SSE nesting bug reproduction tests..."
	uv run pytest tests/client/test_buggy_sse_nesting.py tests/client/test_deep_sse_nesting.py tests/client/test_sse.py::test_nested_sse_server_resolves_correctly -v

check:
	uv run pre-commit run --all-files

docs:
	@echo "Building documentation..."
	@uv run sphinx-build -b html docs docs/_build/html || echo "\n[sphinx-build] Sphinx not installed or configuration missing."
