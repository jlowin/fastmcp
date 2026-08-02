"""Helpers for exposing public names without eagerly importing their modules."""

from collections.abc import Mapping
from importlib import import_module
from typing import Any

LazyImports = Mapping[str, tuple[str, str]]


def resolve_lazy_import(
    name: str,
    package: str,
    namespace: dict[str, Any],
    lazy_imports: LazyImports,
) -> object:
    """Resolve and cache a lazily exported module attribute."""
    try:
        module_name, attr_name = lazy_imports[name]
    except KeyError:
        raise AttributeError(f"module {package!r} has no attribute {name!r}") from None

    value = getattr(import_module(module_name, package), attr_name)
    namespace[name] = value
    return value


def list_module_attributes(
    namespace: dict[str, Any], lazy_imports: LazyImports
) -> list[str]:
    """Include unresolved lazy exports in module introspection."""
    return sorted(namespace.keys() | lazy_imports.keys())
