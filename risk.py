from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

def mk(**kw):
    p = OAuthProxy(
        upstream_authorization_endpoint="https://idp.example.com/authorize",
        upstream_token_endpoint="https://idp.example.com/token",
        upstream_client_id="cid", upstream_client_secret="sec",
        token_verifier=StaticTokenVerifier(tokens={"t": {"client_id": "c"}}),
        jwt_signing_key="x"*64,
        **kw,
    )
    p.get_routes("/mcp")
    return p

# Case A: issuer_url NOT set -> must be identical before/after
a = mk(base_url="https://example.com")
print("A no issuer_url      -> jwt iss:", a.jwt_issuer.issuer)

# Case B: issuer_url set differently -> this is what changes
b = mk(base_url="https://example.com/api", issuer_url="https://example.com")
print("B issuer_url set     -> jwt iss:", b.jwt_issuer.issuer)
