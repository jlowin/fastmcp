"""Regression tests for GitHub token verifier upstream failures."""

import httpx2
import pytest

from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from tests.utilities.httpx2_mock import HTTPXMock

GITHUB_USER_URL = "https://api.github.com/user"


async def test_github_401_is_invalid_token(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=GITHUB_USER_URL,
        status_code=401,
        text="Bad credentials",
    )

    verifier = GitHubTokenVerifier()

    assert await verifier.verify_token("invalid-token") is None


async def test_github_503_propagates_http_status_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=GITHUB_USER_URL,
        status_code=503,
        text="Service unavailable",
    )

    verifier = GitHubTokenVerifier()

    with pytest.raises(httpx2.HTTPStatusError):
        await verifier.verify_token("valid-token")


async def test_github_transport_failure_propagates(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx2.ConnectError("simulated transport failure"),
        url=GITHUB_USER_URL,
    )

    verifier = GitHubTokenVerifier()

    with pytest.raises(httpx2.ConnectError):
        await verifier.verify_token("valid-token")
