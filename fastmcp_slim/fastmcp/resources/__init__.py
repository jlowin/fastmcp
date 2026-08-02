from typing import TYPE_CHECKING

from fastmcp.utilities.lazy_imports import (
    list_module_attributes,
    resolve_lazy_import,
)

if TYPE_CHECKING:
    from .base import Resource as Resource
    from .base import ResourceContent as ResourceContent
    from .base import ResourceResult as ResourceResult
    from .function_resource import FunctionResource as FunctionResource
    from .function_resource import resource as resource
    from .security import ResourceSecurity as ResourceSecurity
    from .template import ResourceTemplate as ResourceTemplate
    from .types import BinaryResource as BinaryResource
    from .types import DirectoryResource as DirectoryResource
    from .types import FileResource as FileResource
    from .types import HttpResource as HttpResource
    from .types import TextResource as TextResource

__all__ = [
    "BinaryResource",
    "DirectoryResource",
    "FileResource",
    "FunctionResource",
    "HttpResource",
    "Resource",
    "ResourceContent",
    "ResourceResult",
    "ResourceSecurity",
    "ResourceTemplate",
    "TextResource",
    "resource",
]

_LAZY_IMPORTS = {
    "BinaryResource": (".types", "BinaryResource"),
    "DirectoryResource": (".types", "DirectoryResource"),
    "FileResource": (".types", "FileResource"),
    "FunctionResource": (".function_resource", "FunctionResource"),
    "HttpResource": (".types", "HttpResource"),
    "Resource": (".base", "Resource"),
    "ResourceContent": (".base", "ResourceContent"),
    "ResourceResult": (".base", "ResourceResult"),
    "ResourceSecurity": (".security", "ResourceSecurity"),
    "ResourceTemplate": (".template", "ResourceTemplate"),
    "TextResource": (".types", "TextResource"),
    "resource": (".function_resource", "resource"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_import(name, __name__, globals(), _LAZY_IMPORTS)


def __dir__() -> list[str]:
    return list_module_attributes(globals(), _LAZY_IMPORTS)
