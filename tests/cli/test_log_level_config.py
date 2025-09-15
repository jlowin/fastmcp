import pytest

from fastmcp.utilities.mcp_server_config import MCPServerConfig


def test_fastmcp_json_log_level():
    """Test that log_level from fastmcp.json is properly applied."""
    # Create a test fastmcp.json with log_level
    config_data = {
        "source": {"path": "test_server.py"},
        "deployment": {"log_level": "DEBUG"},
    }

    config = MCPServerConfig.model_validate(config_data)
    assert config.deployment.log_level == "DEBUG"


@pytest.mark.asyncio
async def test_cli_passes_log_level():
    """Test that CLI correctly passes log_level to server."""
    # This would test the full pipeline
    pass
