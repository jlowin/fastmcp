import pytest
import yaml

from fastmcp import FastMCP
from fastmcp.contrib.transforming_mcp_config.transforming_mcp_config import (
    TransformingMCPConfig,
    TransformingStdioMCPServer,
)
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import Tool as FastMCPTool
from fastmcp.tools.tool_transform import ArgTransformRequest, ToolTransformRequest


def sample_tool_fn(arg1: int, arg2: str) -> str:
    return f"Hello, world! {arg1} {arg2}"


@pytest.fixture
def sample_tool() -> FastMCPTool:
    return FastMCPTool.from_function(sample_tool_fn, name="sample_tool")


async def test_transform_stdio_server(sample_tool: FastMCPTool):
    mcp_config = TransformingMCPConfig(
        mcpServers={
            "stdio": TransformingStdioMCPServer(
                command="uvx",
                args=["mcp-server-fetch"],
                env={"PYTHONIOENCODING": "utf-8"},
                tools={
                    "fetch": ToolTransformRequest(
                        name="run_spot_run",
                        arguments={
                            "url": ArgTransformRequest(
                                name="bark",
                                description="bark bark bark",
                                default="woof woof woof",
                            )
                        },
                    )
                },
            )
        }
    )

    proxy = FastMCP.as_proxy(mcp_config)

    tools = await proxy.get_tools()

    assert "run_spot_run" in tools

    run_spot_run = tools["run_spot_run"]

    assert run_spot_run.name == "run_spot_run"

    with pytest.raises(ToolError, match="Input should be a valid URL"):
        _ = await run_spot_run.run(arguments={"bark": "woof woof woof"})


async def test_transform_stdio_server_from_yaml(sample_tool: FastMCPTool):
    yaml_config = """
    mcpServers:
        fetch:
            command: uvx
            args:
                - mcp-server-fetch
            env:
                PYTHONIOENCODING: utf-8
            tools:
                fetch:
                    name: run_spot_run
                    arguments:
                        url:
                            name: bark
                            description: bark bark bark
                            default: woof woof woof
    """

    mcp_config = TransformingMCPConfig.from_dict(yaml.safe_load(yaml_config))

    proxy = FastMCP.as_proxy(mcp_config)

    tools = await proxy.get_tools()

    assert "run_spot_run" in tools

    run_spot_run = tools["run_spot_run"]

    assert run_spot_run.name == "run_spot_run"

    with pytest.raises(ToolError, match="Input should be a valid URL"):
        _ = await run_spot_run.run(arguments={"bark": "woof woof woof"})


async def test_transform_stdio_server_from_dict(sample_tool: FastMCPTool):
    mcp_config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "env": {"PYTHONIOENCODING": "utf-8"},
                "tools": {
                    "fetch": {
                        "name": "run_spot_run",
                        "arguments": {
                            "url": {
                                "name": "bark",
                                "description": "bark bark bark",
                                "default": "woof woof woof",
                            }
                        },
                    }
                },
            }
        }
    }

    mcp_config = TransformingMCPConfig.from_dict(mcp_config)

    proxy = FastMCP.as_proxy(mcp_config)

    tools = await proxy.get_tools()

    assert "run_spot_run" in tools

    run_spot_run = tools["run_spot_run"]

    assert run_spot_run.name == "run_spot_run"

    with pytest.raises(ToolError, match="Input should be a valid URL"):
        _ = await run_spot_run.run(arguments={"bark": "woof woof woof"})
