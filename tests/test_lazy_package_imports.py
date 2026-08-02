"""Fresh-interpreter guards for lazy public package exports."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize(
    ("statement", "excluded_modules"),
    [
        (
            "from fastmcp.client import BearerAuth",
            (
                "fastmcp.client.auth.client_credentials",
                "fastmcp.client.auth.oauth",
                "fastmcp.client.client",
                "fastmcp.client.transports",
            ),
        ),
        (
            "from fastmcp.client.transports import ClientTransport",
            (
                "fastmcp.client.transports.config",
                "fastmcp.client.transports.http",
                "fastmcp.client.transports.inference",
                "fastmcp.client.transports.memory",
                "fastmcp.client.transports.sse",
                "fastmcp.client.transports.stdio",
            ),
        ),
        (
            "from fastmcp.tools import Tool",
            ("fastmcp.tools.function_tool", "fastmcp.tools.tool_transform"),
        ),
        (
            "from fastmcp.resources import Resource",
            (
                "fastmcp.resources.function_resource",
                "fastmcp.resources.security",
                "fastmcp.resources.template",
                "fastmcp.resources.types",
            ),
        ),
        (
            "from fastmcp.prompts import Prompt",
            ("fastmcp.prompts.function_prompt",),
        ),
        (
            "from fastmcp.server.providers import Provider",
            (
                "fastmcp.server.providers.aggregate",
                "fastmcp.server.providers.fastmcp_provider",
                "fastmcp.server.providers.filesystem",
                "fastmcp.server.providers.local_provider",
                "fastmcp.server.providers.skills",
            ),
        ),
        (
            "from fastmcp.server.middleware import Middleware",
            (
                "fastmcp.server.middleware.authorization",
                "fastmcp.server.middleware.ping",
            ),
        ),
        (
            "from fastmcp.server.transforms import Transform",
            (
                "fastmcp.server.transforms.namespace",
                "fastmcp.server.transforms.prompts_as_tools",
                "fastmcp.server.transforms.resources_as_tools",
                "fastmcp.server.transforms.tool_transform",
                "fastmcp.server.transforms.version_filter",
                "fastmcp.server.transforms.visibility",
            ),
        ),
    ],
)
@pytest.mark.subprocess_heavy
def test_narrow_import_does_not_load_sibling_implementations(
    statement: str, excluded_modules: tuple[str, ...]
) -> None:
    script = textwrap.dedent(
        f"""
        import sys

        {statement}

        excluded = {excluded_modules!r}
        loaded = [
            name
            for name in sys.modules
            if any(name == root or name.startswith(f"{{root}}.") for root in excluded)
        ]
        assert not loaded, loaded
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.subprocess_heavy
def test_all_public_package_exports_resolve() -> None:
    script = textwrap.dedent(
        """
        import importlib

        packages = (
            "fastmcp.client",
            "fastmcp.client.auth",
            "fastmcp.client.transports",
            "fastmcp.prompts",
            "fastmcp.resources",
            "fastmcp.server.middleware",
            "fastmcp.server.providers",
            "fastmcp.server.transforms",
            "fastmcp.tools",
        )
        for package_name in packages:
            package = importlib.import_module(package_name)
            assert set(package.__all__) <= set(dir(package))
            for export in package.__all__:
                assert getattr(package, export) is not None, (package_name, export)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
