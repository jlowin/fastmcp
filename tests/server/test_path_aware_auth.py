from starlette.routing import Route
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from fastmcp.server.auth.auth import OAuthProvider


def test_path_aware_metadata_route():
    """Test that metadata route includes the path component from issuer_url."""
    base_url = "http://localhost:8000"
    issuer_url = "http://localhost:8000/my-server"

    provider = OAuthProvider(
        base_url=base_url,
        issuer_url=issuer_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=["read"], default_scopes=["read"]
        ),
        revocation_options=RevocationOptions(enabled=True),
    )

    routes = provider.get_routes()

    found_metadata = False
    for route in routes:
        if isinstance(route, Route) and "oauth-authorization-server" in route.path:
            if route.path == "/.well-known/oauth-authorization-server/my-server":
                found_metadata = True
                break

    assert found_metadata, "Path-aware metadata route not found"


def test_standard_metadata_route():
    """Test that metadata route is standard when issuer_url has no path (regression check)."""
    base_url = "http://localhost:8000"
    issuer_url = "http://localhost:8000"

    provider = OAuthProvider(
        base_url=base_url,
        issuer_url=issuer_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=["read"], default_scopes=["read"]
        ),
        revocation_options=RevocationOptions(enabled=True),
    )

    routes = provider.get_routes()

    found_metadata = False
    for route in routes:
        if isinstance(route, Route) and "oauth-authorization-server" in route.path:
            if route.path == "/.well-known/oauth-authorization-server":
                found_metadata = True
                break

    assert found_metadata, "Standard metadata route not found"


def test_root_path_metadata_route():
    """Test that metadata route is standard when issuer_url path is just '/'."""
    base_url = "http://localhost:8000"
    issuer_url = "http://localhost:8000/"

    provider = OAuthProvider(
        base_url=base_url,
        issuer_url=issuer_url,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=["read"], default_scopes=["read"]
        ),
        revocation_options=RevocationOptions(enabled=True),
    )

    routes = provider.get_routes()

    found_metadata = False
    for route in routes:
        if isinstance(route, Route) and "oauth-authorization-server" in route.path:
            if route.path == "/.well-known/oauth-authorization-server":
                found_metadata = True
                break

    assert found_metadata, "Standard metadata route not found for root path"
