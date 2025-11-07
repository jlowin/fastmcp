"""Shared fixtures for task tests."""

import pytest

from fastmcp.utilities.tests import temporary_settings


@pytest.fixture(autouse=True)
async def enable_docket_and_tasks():
    """Enable Docket and task protocol support for all task tests."""
    with temporary_settings(
        experimental__enable_docket=True,
        experimental__enable_tasks=True,
    ):
        # Verify both are enabled
        import fastmcp

        assert fastmcp.settings.experimental.enable_docket, (
            "Docket should be enabled after fixture"
        )
        assert fastmcp.settings.experimental.enable_tasks, (
            "Tasks should be enabled after fixture"
        )

        yield

        # Clean up global task storage to prevent test pollution
        from fastmcp.server.tasks import _temporary_docket_shims, _temporary_mcp_shims

        _temporary_docket_shims._task_states.clear()
        _temporary_docket_shims._task_results.clear()
        _temporary_docket_shims._task_keep_alive.clear()
        _temporary_mcp_shims._task_id_mapping.clear()

        # Clear function wrapper cache to prevent accumulation
        _temporary_docket_shims.wrap_function_for_result_storage.cache_clear()
