import pytest

from fastmcp.server.auth.oidc_proxy import clear_oidc_discovery_cache


@pytest.fixture(autouse=True)
def clear_discovery_cache():
    """Isolate tests from the process-local OIDC discovery cache.

    Discovery results are cached per config URL for the life of the process, and
    auth tests reuse a handful of config URLs across modules, so without this a
    mocked discovery response from one test would satisfy the next one.
    """
    clear_oidc_discovery_cache()

    yield

    clear_oidc_discovery_cache()
