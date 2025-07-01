# Proxy-friendly TokenHandler that skips redirect_uri + PKCE checks for authorization_code grant
from __future__ import annotations

from typing import Any

import base64
import hashlib
import time

from pydantic import ValidationError
from starlette.requests import Request
from starlette.routing import Route

from mcp.server.auth.handlers.token import (
    TokenHandler,
    AuthorizationCodeRequest,
    RefreshTokenRequest,
    TokenRequest,
    TokenErrorResponse,
    TokenSuccessResponse,
)
from mcp.server.auth.middleware.client_auth import ClientAuthenticator, AuthenticationError
from mcp.server.auth.provider import OAuthAuthorizationServerProvider, TokenError, AuthorizationCode
from mcp.shared.auth import OAuthToken

from fastmcp.utilities.logging import get_logger

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = get_logger(__name__)

class ProxyTokenHandler(TokenHandler):
    """Version of TokenHandler that disables redirect_uri and PKCE validation.

    This is required for TransparentOAuthProxyProvider because the proxy never
    issued the authorization code itself, so it cannot know the original
    redirect_uri or code_challenge.
    """

    def __init__(
        self,
        provider: OAuthAuthorizationServerProvider[Any, Any, Any],
        client_authenticator: ClientAuthenticator,
    ) -> None:
        super().__init__(provider, client_authenticator)

    # pylint: disable=too-many-return-statements,too-many-branches
    async def handle(self, request: Request):  # noqa: C901 (keep parity with upstream)
        # Emit a log entry so that calling code can verify that the proxy route
        # is being invoked instead of the default MCP TokenHandler.
        logger.debug("ProxyTokenHandler invoked for /token request from %s", request.client)

        # Log the raw request form data (with sensitive fields redacted)
        try:
            # NOTE: We cannot reuse *form_data* parsed later because we only
            # have one shot at reading the body.  Here we read it into memory
            # first so we can log and then parse.
            raw_body = await request.body()
            from urllib.parse import parse_qs

            parsed_qs = parse_qs(raw_body.decode())
            redacted: dict[str, str] = {}
            for k, v in parsed_qs.items():
                value = v[0] if v else ""
                if k in {"client_secret", "code", "refresh_token"}:
                    redacted[k] = value[:8] + "…" if value else ""
                else:
                    redacted[k] = value
            logger.debug("/token request form from client: %s", redacted)
            # Re-create the request stream for downstream parsing
            request._body = raw_body  # type: ignore[attr-defined]  # pylint: disable=protected-access
        except Exception:  # noqa: BLE001
            logger.debug("Unable to log raw form body", exc_info=True)

        try:
            form_data = await request.form()
            token_request = TokenRequest.model_validate(dict(form_data)).root
        except ValidationError as validation_error:  # pragma: no cover
            return self.response(
                TokenErrorResponse(
                    error="invalid_request",
                    error_description=str(validation_error),
                )
            )

        try:
            client_info = await self.client_authenticator.authenticate(
                client_id=token_request.client_id,
                client_secret=token_request.client_secret,
            )
        except AuthenticationError as e:
            logger.warning("unauthorized_client: authentication failed (%s)", e)
            return self.response(
                TokenErrorResponse(
                    error="unauthorized_client",
                    error_description=e.message,
                )
            )

        if token_request.grant_type not in client_info.grant_types:
            logger.warning("unsupported_grant_type: %s not in %s", token_request.grant_type, client_info.grant_types)
            return self.response(
                TokenErrorResponse(
                    error="unsupported_grant_type",
                    error_description=(
                        f"Unsupported grant type (supported grant types are " f"{client_info.grant_types})"
                    ),
                )
            )

        tokens: OAuthToken

        match token_request:
            case AuthorizationCodeRequest():
                # -----------------------------------------------------------------
                # Modified branch: skip redirect_uri and PKCE verification.
                # -----------------------------------------------------------------
                logger.debug("Processing authorization_code grant via proxy handler")
                auth_code = await self.provider.load_authorization_code(
                    client_info, token_request.code
                )
                if auth_code is None or auth_code.client_id != token_request.client_id:
                    logger.warning("invalid_grant: authorization code not found or client mismatch")
                    return self.response(
                        TokenErrorResponse(
                            error="invalid_grant",
                            error_description="authorization code does not exist",
                        )
                    )

                # Ensure the upstream token endpoint receives redirect_uri if the
                # client supplied one.  Some IdPs (e.g., Autodesk Forge) treat
                # it as mandatory even when PKCE is used.

                if token_request.redirect_uri is not None:
                    # Recreate AuthorizationCode with updated redirect_uri while
                    # avoiding duplicate keyword arguments.
                    auth_code_data = auth_code.model_dump(
                        exclude={"redirect_uri", "redirect_uri_provided_explicitly"}
                    )
                    auth_code = AuthorizationCode(
                        **auth_code_data,
                        redirect_uri=token_request.redirect_uri,
                        redirect_uri_provided_explicitly=True,
                    )

                try:
                    # Attach code_verifier so provider can access it even if
                    # the form body is no longer available.
                    setattr(auth_code, "_code_verifier", token_request.code_verifier)

                    tokens = await self.provider.exchange_authorization_code(
                        client_info, auth_code
                    )
                except TokenError as e:
                    logger.warning("token error from provider: %s", e)
                    return self.response(
                        TokenErrorResponse(
                            error=e.error,
                            error_description=e.error_description,
                        )
                    )

            case RefreshTokenRequest():
                # Unchanged logic copied from upstream TokenHandler
                logger.debug("Processing refresh_token grant via proxy handler")
                refresh_token = await self.provider.load_refresh_token(
                    client_info, token_request.refresh_token
                )
                if refresh_token is None or refresh_token.client_id != token_request.client_id:
                    logger.warning("invalid_grant: refresh token not found or client mismatch")
                    return self.response(
                        TokenErrorResponse(
                            error="invalid_grant",
                            error_description="refresh token does not exist",
                        )
                    )

                if refresh_token.expires_at and refresh_token.expires_at < time.time():
                    logger.warning("invalid_grant: refresh token expired")
                    return self.response(
                        TokenErrorResponse(
                            error="invalid_grant",
                            error_description="refresh token has expired",
                        )
                    )

                scopes = token_request.scope.split(" ") if token_request.scope else refresh_token.scopes
                for scope in scopes:
                    if scope not in refresh_token.scopes:
                        logger.warning("invalid_scope: requested scope not in refresh token")
                        return self.response(
                            TokenErrorResponse(
                                error="invalid_scope",
                                error_description=(
                                    f"cannot request scope `{scope}` " "not provided by refresh token"
                                ),
                            )
                        )

                try:
                    tokens = await self.provider.exchange_refresh_token(
                        client_info, refresh_token, scopes
                    )
                except TokenError as e:
                    logger.warning("token error from provider during refresh: %s", e)
                    return self.response(
                        TokenErrorResponse(
                            error=e.error,
                            error_description=e.error_description,
                        )
                    )
        return self.response(TokenSuccessResponse(root=tokens))

        # ----------------------------
        # Successful response to client
        # ----------------------------

        try:
            redacted_tokens = {
                "access_token": tokens.access_token[:8] + "…",  # type: ignore[attr-defined]
                "expires_in": getattr(tokens, "expires_in", None),
                "refresh_token": (
                    tokens.refresh_token[:8] + "…"  # type: ignore[attr-defined]
                    if getattr(tokens, "refresh_token", None)
                    else None
                ),
                "token_type": getattr(tokens, "token_type", "bearer"),
            }
            logger.debug("/token success response to client: %s", redacted_tokens)
        except Exception:  # noqa: BLE001
            logger.debug("Failed to log token response", exc_info=True)

        return self.response(TokenSuccessResponse(root=tokens)) 