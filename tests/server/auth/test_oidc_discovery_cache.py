from unittest.mock import MagicMock, patch

import pytest
from httpx2 import Response
from pydantic import AnyHttpUrl

from fastmcp.server.auth.oidc_proxy import OIDCConfiguration

CONFIG_URL = AnyHttpUrl(
    "https://cache-test.example.com/.well-known/openid-configuration"
)
VALID_DOCUMENT = {
    "issuer": "https://cache-test.example.com",
    "authorization_endpoint": "https://cache-test.example.com/authorize",
    "token_endpoint": "https://cache-test.example.com/token",
    "jwks_uri": "https://cache-test.example.com/jwks",
    "response_types_supported": ["code"],
    "subject_types_supported": ["public"],
    "id_token_signing_alg_values_supported": ["RS256"],
}


@pytest.fixture(autouse=True)
def clear_discovery_cache():
    OIDCConfiguration._clear_discovery_cache()
    yield
    OIDCConfiguration._clear_discovery_cache()


def _response(document=None):
    response = MagicMock(spec=Response)
    response.json.return_value = dict(document or VALID_DOCUMENT)
    return response


def test_reuses_successful_discovery_document():
    with patch("httpx2.get", return_value=_response()) as get:
        first = OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )
        second = OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )

    assert first == second
    assert first is not second
    get.assert_called_once()


def test_expired_discovery_document_is_refetched():
    with (
        patch(
            "fastmcp.server.auth.oidc_proxy.monotonic",
            side_effect=[0.0, 301.0],
        ),
        patch("httpx2.get", side_effect=[_response(), _response()]) as get,
    ):
        OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )
        OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )

    assert get.call_count == 2


def test_cached_document_does_not_share_mutable_state():
    with patch("httpx2.get", return_value=_response()) as get:
        first = OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )
        first.response_types_supported = ["mutated"]
        second = OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )

    assert second.response_types_supported == ["code"]
    get.assert_called_once()


def test_failed_discovery_is_not_cached():
    with patch(
        "httpx2.get", side_effect=[RuntimeError("boom"), _response()]
    ) as get:
        with pytest.raises(RuntimeError, match="boom"):
            OIDCConfiguration.get_oidc_configuration(
                CONFIG_URL, strict=True, timeout_seconds=10
            )
        OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=True, timeout_seconds=10
        )

    assert get.call_count == 2


def test_strict_is_applied_per_call_without_refetch():
    document = dict(VALID_DOCUMENT)
    document.pop("subject_types_supported")
    with patch("httpx2.get", return_value=_response(document)) as get:
        OIDCConfiguration.get_oidc_configuration(
            CONFIG_URL, strict=False, timeout_seconds=10
        )
        with pytest.raises(
            ValueError, match="Missing required configuration metadata"
        ):
            OIDCConfiguration.get_oidc_configuration(
                CONFIG_URL, strict=True, timeout_seconds=10
            )

    get.assert_called_once()
