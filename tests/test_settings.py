import pytest

from fastmcp.settings import Settings


def test_http_host_origin_protection_defaults_to_false():
    assert Settings().http_host_origin_protection is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("auto", "auto"),
        ("true", True),
        ("false", False),
    ],
)
def test_http_host_origin_protection_env_var(value, expected, monkeypatch):
    monkeypatch.setenv("FASTMCP_HTTP_HOST_ORIGIN_PROTECTION", value)

    assert Settings().http_host_origin_protection == expected


def test_encryption_key_defaults_to_none(monkeypatch):
    monkeypatch.delenv("FASTMCP_ENCRYPTION_KEY", raising=False)

    assert Settings().encryption_key is None


def test_encryption_key_env_var(monkeypatch):
    monkeypatch.setenv("FASTMCP_ENCRYPTION_KEY", "s3kr1t-material")

    key = Settings().encryption_key
    assert key is not None
    assert key.get_secret_value() == "s3kr1t-material"


def test_encryption_key_is_not_printable(monkeypatch):
    """A settings dump must never carry the key into a log."""
    monkeypatch.setenv("FASTMCP_ENCRYPTION_KEY", "s3kr1t-material")

    assert "s3kr1t-material" not in repr(Settings())
