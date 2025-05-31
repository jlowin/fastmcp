import asyncio

import pytest


@pytest.fixture(autouse=True)
def reset_asyncio_state():
    yield
    # Reset after each module
    asyncio.set_child_watcher(None)  # type: ignore[reportCallIssue]
    # Close any existing loops
    try:
        loop = asyncio.get_running_loop()
        loop.close()
    except RuntimeError:
        pass
