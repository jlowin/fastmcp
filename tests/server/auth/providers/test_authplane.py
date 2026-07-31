import pytest

from fastmcp.server.auth.providers.authplane import AuthPlaneAuthProvider


def test_authplane_basic_init():
    auth = AuthPlaneAuthProvider(
        server_url="https://auth.example.com",
        base_url="http://localhost:8000",
    )
    assert auth is not None


def test_authplane_jwks_uri():
    auth = AuthPlaneAuthProvider(
        server_url="https://auth.example.com/",
        base_url="http://localhost:8000",
    )
    verifier = auth.token_verifier
    assert verifier.jwks_uri == "https://auth.example.com/.well-known/jwks.json"
