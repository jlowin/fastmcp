# Local Keycloak Instance Setup

This guide shows how to set up a local Keycloak instance for testing the FastMCP Keycloak OAuth example.

## Quick Start

**Prerequisites**: Docker and Docker Compose must be installed.

Start the local Keycloak instance with Docker Compose:

```bash
cd examples/auth/keycloak_auth/keycloak
./start-keycloak.sh
```

This script will:
- Start a Keycloak container on port 8080
- Automatically import the preconfigured/customized `fastmcp` realm from [`realm-fastmcp.json`](realm-fastmcp.json)
- Create a test user (`testuser` / `password123`)


**Keycloak Admin Console**: [http://localhost:8080/admin](http://localhost:8080/admin) (admin / admin123)

## Preconfigured Realm

The Docker setup automatically imports a preconfigured realm configured for dynamic client registration. The default settings are described below and can be adjusted or complemented as needed by editing the [`realm-fastmcp.json`](realm-fastmcp.json) file before starting Keycloak. If settings are changed after Keycloak has been started, restart Keycloak with

```bash
docker-compose restart
```

to apply the changes.

### Realm: `fastmcp`

The realm is configured with:

- **Dynamic Client Registration** enabled for `http://localhost:8000/*`
- **Registration Allowed**: Yes
- **Allowed Client Scopes**: `openid`, `profile`, `email`, `roles`, `offline_access`, `web-origins`, `basic`
- **Trusted Hosts**: `localhost`, `172.17.0.1`, `172.18.0.1`

### Test User

The realm includes a test user:

- **Username**: `testuser`
- **Password**: `password123`
- **Email**: `testuser@example.com`
- **First Name**: Test
- **Last Name**: User

### Dynamic Client Registration

The FastMCP server will automatically register a client with Keycloak on first run. The client registration policy ensures:

- Client URIs must match `http://localhost:8000/*`
- Only allowed client scopes can be requested
- Client registration requests must come from trusted hosts

### Token Claims

Access tokens include standard OpenID Connect claims:
- `sub`: User identifier
- `preferred_username`: Username
- `email`: User email address
- `given_name`: First name
- `family_name`: Last name
- `realm_access`: Realm-level roles
- `resource_access`: Client-specific roles

## Docker Configuration

The setup uses the following Docker configuration:

- **Container name**: `keycloak-fastmcp`
- **Port**: `8080`
- **Database**: H2 (in-memory, for development only)
- **Admin credentials**: `admin` / `admin123`
- **Realm import**: `realm-fastmcp.json`

For production use, consider:
- Using a persistent database (PostgreSQL, MySQL)
- Configuring HTTPS
- Using proper admin credentials
- Enabling audit logging
- Restricting dynamic client registration or using pre-registered clients

## Troubleshooting

### View Keycloak Logs

```bash
docker-compose logs -f keycloak
```

### Common Issues

1. **Keycloak not starting**
   - Check Docker is running: `docker ps`
   - Check port 8080 is not in use:
     - Linux/macOS: `netstat -an | grep 8080` or `lsof -i :8080`
     - Windows: `netstat -an | findstr 8080`

2. **Realm not found**
   - Verify realm import: Check admin console at [http://localhost:8080/admin](http://localhost:8080/admin)
   - Check realm file exists:
     - Linux/macOS: `ls realm-fastmcp.json`
     - Windows: `dir realm-fastmcp.json`

3. **Client registration failed**
   - Verify the request comes from a trusted host
   - Check that redirect URIs match the allowed pattern (`http://localhost:8000/*`)
   - Review client registration policies in the admin console

4. **"Client not found" error after Keycloak restart**
   - This can happen when Keycloak is restarted and the previously registered OAuth client no longer exists
   - **No action needed**: The FastMCP OAuth client automatically detects this condition and re-registers with Keycloak
   - Simply run your client again and it will automatically handle the re-registration process
