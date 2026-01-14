"""Default trusted CIMD domains for FastMCP.

CIMD (Client ID Metadata Document) domains listed here can bypass consent screens
when authenticating with FastMCP servers. By default, this list is empty - all
CIMD clients will see a consent screen showing their verified domain.

Server operators can configure trusted domains via CIMDTrustPolicy:

    OAuthProxy(
        ...,
        cimd_trust_policy=CIMDTrustPolicy(
            trusted_domains=["vscode.dev", "my-corp.com"],
        ),
    )

Subdomain matching is enabled, so trusting "example.com" also trusts "*.example.com".

Known CIMD documents (for reference, not auto-trusted):
- https://vscode.dev/oauth/client-metadata.json
- https://insiders.vscode.dev/oauth/client-metadata.json
- https://www.mcpjam.com/.well-known/oauth/client-metadata.json
"""

# Server operators can configure trusted domains based on their requirements.
TRUSTED_CIMD_DOMAINS: list[str] = []
