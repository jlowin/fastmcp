from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthToken,
)


class BearerTokenValidatorProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """
    A minimal OAuth provider that only validates pre-existing bearer tokens.
    It does not support token issuance, client registration, or other
    full OAuth server functionalities.
    """

    async def load_access_token(self, token: str) -> AccessToken | None:
        """
        Validates the provided bearer token.
        Replace the dummy logic below with your actual token validation.
        This could involve:
        - Decoding and verifying a JWT.
        - Calling an introspection endpoint on your hosting platform's auth server.
        - Checking the token against a database or cache.
        """
        print(f"Attempting to validate token: {token[:20]}...")  # Basic logging

        # --- DUMMY VALIDATION LOGIC ---
        # Replace this with your actual token validation mechanism.
        if token == "VALID_BEARER_TOKEN_FROM_HOSTING_PLATFORM":
            # If the token is valid, return an AccessToken object.
            # The client_id and scopes should ideally be derived from the token itself
            # (e.g., from JWT claims or an introspection response).
            return AccessToken(
                token=token,
                client_id="client_id_from_token_payload",  # e.g., user ID or app ID
                scopes=["read_data", "execute_tool"],  # Scopes granted by this token
                expires_at=None,  # Optionally set token expiry if known
            )
        elif token == "EXPIRED_BEARER_TOKEN":
            # Example: if your validation can detect expired tokens
            print("Token is expired.")
            return None  # Returning None signifies an invalid/expired token
        # --- END DUMMY VALIDATION LOGIC ---

        print("Token is invalid.")
        return None  # Token is invalid

    # --- Methods below are not used for simple bearer token validation ---
    # --- They relate to the server acting as a full OAuth issuer. ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        # This method is called by the TokenHandler if the /token endpoint is hit.
        # In a bearer-token-only setup, the /token endpoint of this MCP server
        # should ideally not be used. Raising NotImplementedError is appropriate.
        raise NotImplementedError(
            "Client management is not supported by this provider."
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError(
            "Client registration is not supported by this provider."
        )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        raise NotImplementedError(
            "Authorization code flow is not supported by this provider."
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        raise NotImplementedError(
            "Authorization code flow is not supported by this provider."
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        raise NotImplementedError(
            "Authorization code exchange is not supported by this provider."
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        raise NotImplementedError(
            "Refresh token flow is not supported by this provider."
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        raise NotImplementedError(
            "Refresh token exchange is not supported by this provider."
        )

    async def revoke_token(
        self,
        token: AccessToken | RefreshToken,
    ) -> None:
        raise NotImplementedError("Token revocation is not supported by this provider.")
