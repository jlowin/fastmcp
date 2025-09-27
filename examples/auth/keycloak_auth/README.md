# Keycloak OAuth Example

This example demonstrates how to protect a FastMCP server with Keycloak using OAuth 2.0/OpenID Connect.

## Features

- **Local Keycloak Instance**: Complete Docker setup with preconfigured realm
- **Dynamic Client Registration**: Automatic OIDC endpoint discovery
- **Pre-configured Test User**: Ready-to-use credentials for testing
- **JWT Token Verification**: Secure token validation with JWKS

## Quick Start

### 1. Start Keycloak

```bash
cd examples/auth/keycloak_auth
./start-keycloak.sh
```

Wait for Keycloak to be ready (check with `docker logs -f keycloak-fastmcp`).

### 2. Verify Keycloak Setup

Open [http://localhost:8080](http://localhost:8080) in your browser:

- **Admin Console**: [http://localhost:8080/admin](http://localhost:8080/admin)
  - Username: `admin`
  - Password: `admin123`
- **FastMCP Realm**: [http://localhost:8080/realms/fastmcp](http://localhost:8080/realms/fastmcp)

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

The default configuration works with the Docker setup:

```env
FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL=http://localhost:8080/realms/fastmcp
FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL=http://localhost:8000
```

### 5. Start the FastMCP Server

```bash
python server.py
```

### 6. Test with Client

```bash
python client.py
```

The client will:
1. Open your browser to Keycloak login page
2. Authenticate and redirect back to the client
3. Call protected FastMCP tools
4. Display user information from the access token

## Test Credentials

The preconfigured realm includes a test user:

- **Username**: `testuser`
- **Password**: `password123`
- **Email**: `testuser@example.com`

## Keycloak Configuration

### Realm: `fastmcp`

The Docker setup automatically imports a preconfigured realm with:

- **Client ID**: `fastmcp-client`
- **Client Secret**: `fastmcp-client-secret-12345`
- **Redirect URIs**: `http://localhost:8000/auth/callback`, `http://localhost:8000/*`
- **Scopes**: `openid`, `profile`, `email`

### Client Configuration

The client is configured for:
- **Authorization Code Flow** (recommended for server-side applications)
- **Dynamic Client Registration** supported
- **PKCE** enabled for additional security
- **JWT Access Tokens** with RS256 signature

### Token Claims

The access tokens include:
- `sub`: User identifier
- `preferred_username`: Username
- `email`: User email address
- `realm_access`: Realm-level roles
- `resource_access`: Client-specific roles

## Advanced Configuration

### Custom Realm Configuration

To use your own Keycloak realm:

1. Update the realm URL in `.env`:
   ```env
   FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL=https://your-keycloak.com/realms/your-realm
   ```

2. Ensure your client is configured with:
   - Authorization Code Flow enabled
   - Correct redirect URIs
   - Required scopes (minimum: `openid`)

### Production Deployment

For production use:

1. **Use HTTPS**: Update all URLs to use HTTPS
2. **Secure Client Secret**: Use environment variables or secret management
3. **Configure CORS**: Set appropriate web origins in Keycloak
4. **Token Validation**: Consider shorter token lifespans
5. **Logging**: Adjust log levels for production

### Custom Token Verifier

You can provide a custom JWT verifier:

```python
from fastmcp.server.auth.providers.jwt import JWTVerifier

custom_verifier = JWTVerifier(
    jwks_uri="https://your-keycloak.com/realms/your-realm/protocol/openid-connect/certs",
    issuer="https://your-keycloak.com/realms/your-realm",
    audience="your-client-id",
    required_scopes=["api:read", "api:write"]
)

auth = KeycloakAuthProvider(
    realm_url="https://your-keycloak.com/realms/your-realm",
    base_url="https://your-fastmcp-server.com",
    token_verifier=custom_verifier,
)
```

## Troubleshooting

### Common Issues

1. **"Failed to discover Keycloak endpoints"**
   - Check that Keycloak is running: `docker-compose ps`
   - Verify the realm URL is correct
   - Ensure the realm exists in Keycloak

2. **"Invalid redirect URI"**
   - Check that the redirect URI in your client matches the base_url
   - Default should be: `http://localhost:8000/auth/callback`

3. **"Token verification failed"**
   - Verify the JWKS URI is accessible
   - Check that the token issuer matches your realm
   - Ensure required scopes are configured

4. **"Authentication failed"**
   - Try the test user credentials: `testuser` / `password123`
   - Check Keycloak admin console for user status
   - Verify client configuration in Keycloak

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Keycloak Logs

View Keycloak container logs:

```bash
docker-compose logs -f keycloak
```

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │    │   FastMCP   │    │  Keycloak   │
│             │    │   Server    │    │             │
└─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │
       │  1. Call tool     │                   │
       ├──────────────────►│                   │
       │                   │ 2. Redirect to    │
       │                   │    OAuth login    │
       │                   ├──────────────────►│
       │  3. Auth redirect │                   │
       │◄──────────────────────────────────────┤
       │                   │                   │
       │  4. Login & authorize                 │
       ├──────────────────────────────────────►│
       │                   │                   │
       │  5. Auth code     │                   │
       │◄──────────────────┤                   │
       │                   │ 6. Exchange code  │
       │                   │    for tokens     │
       │                   ├──────────────────►│
       │                   │                   │
       │  7. Tool response │ 8. Verify token   │
       │◄──────────────────┤                   │
       │                   │                   │
```

## Security Considerations

- **HTTPS Only**: Always use HTTPS in production
- **Token Expiration**: Configure appropriate token lifespans
- **Scope Validation**: Use least-privilege scopes
- **CORS Configuration**: Restrict origins appropriately
- **Client Secrets**: Store securely and rotate regularly
- **Audit Logging**: Enable Keycloak event logging

## Related Documentation

- [FastMCP Authentication Guide](https://docs.fastmcp.com/auth)
- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [OAuth 2.0 RFC](https://tools.ietf.org/html/rfc6749)
- [OpenID Connect Specification](https://openid.net/specs/openid-connect-core-1_0.html)