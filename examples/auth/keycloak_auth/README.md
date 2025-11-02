# Keycloak OAuth Example

Demonstrates FastMCP server protection with Keycloak OAuth.

## Setup

### 1. Prepare the Realm Configuration

Review the realm configuration file: [`keycloak/realm-fastmcp.json`](keycloak/realm-fastmcp.json)

**Optional**: Customize the file for your environment:
- **Realm name**: Change `"realm": "fastmcp"` to match your project
- **Trusted hosts**: Update the `"trusted-hosts"` section for your environment
- **Test user**: Review credentials (`testuser` / `password123`) and change for security

### 2. Set Up Keycloak

Choose one of the following options:

#### Option A: Local Keycloak Instance (Recommended for Testing)

See [keycloak/README.md](keycloak/README.md) for details.

**Note:** The realm will be automatically imported on startup.

#### Option B: Existing Keycloak Instance

Manually import the realm:
- Log in to your Keycloak Admin Console
- Click **Manage realms** → **Create realm**
- Drag the `realm-fastmcp.json` file into the **Resource file** box
- Click **Create**

### 3. Run the Example

1. Set environment variables:

   ```bash
   export FASTMCP_SERVER_AUTH_KEYCLOAK_REALM_URL="http://localhost:8080/realms/fastmcp"
   export FASTMCP_SERVER_AUTH_KEYCLOAK_BASE_URL="http://localhost:8000"
   ```

2. Run the server:

   ```bash
   python server.py
   ```

3. In another terminal, run the client:

   ```bash
   python client.py
   ```

The client will open your browser for Keycloak authentication.
