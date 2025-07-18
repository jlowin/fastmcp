"""FastMCP - A more ergonomic interface for MCP servers."""

from __future__ import annotations

import datetime
from datetime import timedelta
import inspect
import re
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    asynccontextmanager,
)
from dataclasses import dataclass
from functools import partial, lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Literal, cast, overload
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from typing import Any, Dict, List, Optional
import asyncio
import abc
import httpx
import logging
import time
import hashlib
import sqlite3
import urllib.parse
import secrets
from typing import Tuple
import base64

import anyio
import httpx
import mcp.types
import uvicorn
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.lowlevel.server import LifespanResultT, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    AnyFunction,
    ContentBlock,
    GetPromptResult,
    ToolAnnotations,
)
from mcp.types import Prompt as MCPPrompt
from mcp.types import Resource as MCPResource
from mcp.types import ResourceTemplate as MCPResourceTemplate
from mcp.types import Tool as MCPTool
from pydantic import AnyUrl
from starlette.middleware import Middleware as ASGIMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

import fastmcp
import fastmcp.server
from fastmcp.exceptions import DisabledError, NotFoundError
from fastmcp.mcp_config import MCPConfig
from fastmcp.prompts import Prompt, PromptManager
from fastmcp.prompts.prompt import FunctionPrompt
from fastmcp.resources import Resource, ResourceManager
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.auth.auth import OAuthProvider
from fastmcp.server.auth.providers.bearer_env import EnvBearerAuthProvider
from fastmcp.server.http import (
    StarletteWithLifespan,
    create_sse_app,
    create_streamable_http_app,
)
from fastmcp.server.low_level import LowLevelServer
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.settings import Settings
from fastmcp.tools import ToolManager
from fastmcp.tools.tool import FunctionTool, Tool, ToolResult
from fastmcp.utilities.cache import TimedCache
from fastmcp.utilities.cli import log_server_banner
from fastmcp.utilities.components import FastMCPComponent
from fastmcp.utilities.logging import get_logger
from fastmcp.utilities.types import NotSet, NotSetT

if TYPE_CHECKING:
    from fastmcp.client import Client
    from fastmcp.client.transports import ClientTransport, ClientTransportT
    from fastmcp.server.openapi import ComponentFn as OpenAPIComponentFn
    from fastmcp.server.openapi import FastMCPOpenAPI, RouteMap
    from fastmcp.server.openapi import RouteMapFn as OpenAPIRouteMapFn
    from fastmcp.server.proxy import FastMCPProxy
logger = get_logger(__name__)

DuplicateBehavior = Literal["warn", "error", "replace", "ignore"]
Transport = Literal["stdio", "http", "sse", "streamable-http"]

# Compiled URI parsing regex to split a URI into protocol and path components
URI_PATTERN = re.compile(r"^([^:]+://)(.*?)$")


class OAuth2Storage:
    """Persistent storage for OAuth2 clients and tokens using SQLite."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize OAuth2 storage with SQLite database."""
        self.db_path = db_path or "oauth2.db"
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable optimizations
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA cache_size=1000')
            conn.execute('PRAGMA temp_store=MEMORY')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    client_secret_hash TEXT NOT NULL,
                    client_name TEXT NOT NULL,
                    redirect_uris TEXT NOT NULL,  -- JSON array
                    grant_types TEXT NOT NULL,   -- JSON array
                    scopes TEXT,                 -- JSON array
                    token_endpoint_auth_method TEXT DEFAULT 'client_secret_basic',
                    client_secret_expires_at INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    token_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    access_token_hash TEXT NOT NULL,
                    token_type TEXT DEFAULT 'Bearer',
                    expires_at TIMESTAMP NOT NULL,
                    scopes TEXT,  -- JSON array
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES oauth_clients (client_id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS oauth_auth_codes (
                    code_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    scopes TEXT,  -- JSON array
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES oauth_clients (client_id)
                )
            ''')
            
            # Create indexes for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tokens_client_id ON oauth_tokens(client_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tokens_expires_at ON oauth_tokens(expires_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tokens_hash ON oauth_tokens(access_token_hash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_auth_codes_expires_at ON oauth_auth_codes(expires_at)')
    
    def _hash_secret(self, secret: str) -> str:
        """Hash a secret using SHA-256."""
        return hashlib.sha256(secret.encode()).hexdigest()
    
    def _verify_secret(self, secret: str, hash_value: str) -> bool:
        """Verify a secret against its hash."""
        return hashlib.sha256(secret.encode()).hexdigest() == hash_value
    
    def register_client(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new OAuth2 client."""
        with self._lock:
            client_id = f"mcp-client-{secrets.token_urlsafe(16)}"
            client_secret = secrets.token_urlsafe(32)
            client_secret_hash = self._hash_secret(client_secret)
            
            redirect_uris = json.dumps(client_data.get('redirect_uris', []))
            grant_types = json.dumps(client_data.get('grant_types', ['authorization_code']))
            scopes = json.dumps(client_data.get('scopes', ['read', 'write']))
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO oauth_clients 
                    (client_id, client_secret_hash, client_name, redirect_uris, 
                     grant_types, scopes, token_endpoint_auth_method, client_secret_expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    client_id,
                    client_secret_hash,
                    client_data.get('client_name', 'MCP Client'),
                    redirect_uris,
                    grant_types,
                    scopes,
                    client_data.get('token_endpoint_auth_method', 'client_secret_basic'),
                    client_data.get('client_secret_expires_at', 0)
                ))
            
            logger.info(f"Registered new OAuth2 client: {client_id}")
            
            return {
                'client_id': client_id,
                'client_secret': client_secret,
                'client_name': client_data.get('client_name', 'MCP Client'),
                'redirect_uris': client_data.get('redirect_uris', []),
                'grant_types': client_data.get('grant_types', ['authorization_code']),
                'scopes': client_data.get('scopes', ['read', 'write']),
                'token_endpoint_auth_method': client_data.get('token_endpoint_auth_method', 'client_secret_basic'),
                'client_secret_expires_at': client_data.get('client_secret_expires_at', 0)
            }
    
    def validate_client_credentials(self, client_id: str, client_secret: str) -> Optional[Dict[str, Any]]:
        """Validate client credentials and return client info if valid."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT client_id, client_secret_hash, client_name, redirect_uris, 
                           grant_types, scopes, token_endpoint_auth_method, client_secret_expires_at
                    FROM oauth_clients 
                    WHERE client_id = ?
                ''', (client_id,))
                
                client = cursor.fetchone()
                
                if not client:
                    logger.warning(f"Client not found: {client_id}")
                    return None
                
                # Check if client secret has expired
                if client['client_secret_expires_at'] > 0 and time.time() > client['client_secret_expires_at']:
                    logger.warning(f"Client secret expired for: {client_id}")
                    return None
                
                # Verify client secret
                if not self._verify_secret(client_secret, client['client_secret_hash']):
                    logger.warning(f"Invalid client secret for: {client_id}")
                    return None
                
                return {
                    'client_id': client['client_id'],
                    'client_name': client['client_name'],
                    'redirect_uris': json.loads(client['redirect_uris']),
                    'grant_types': json.loads(client['grant_types']),
                    'scopes': json.loads(client['scopes']),
                    'token_endpoint_auth_method': client['token_endpoint_auth_method']
                }
    
    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get client information by client_id."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT client_id, client_name, redirect_uris, grant_types, scopes, 
                           token_endpoint_auth_method, client_secret_expires_at
                    FROM oauth_clients 
                    WHERE client_id = ?
                ''', (client_id,))
                
                client = cursor.fetchone()
                
                if not client:
                    return None
                
                return {
                    'client_id': client['client_id'],
                    'client_name': client['client_name'],
                    'redirect_uris': json.loads(client['redirect_uris']),
                    'grant_types': json.loads(client['grant_types']),
                    'scopes': json.loads(client['scopes']),
                    'token_endpoint_auth_method': client['token_endpoint_auth_method'],
                    'client_secret_expires_at': client['client_secret_expires_at']
                }
    
    def store_access_token(self, client_id: str, access_token: str, expires_in: int, scopes: List[str]) -> str:
        """Store an access token and return token ID."""
        with self._lock:
            token_id = secrets.token_urlsafe(16)
            access_token_hash = self._hash_secret(access_token)
            expires_at = datetime.datetime.utcnow() + timedelta(seconds=expires_in)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO oauth_tokens 
                    (token_id, client_id, access_token_hash, expires_at, scopes)
                    VALUES (?, ?, ?, ?, ?)
                ''', (token_id, client_id, access_token_hash, expires_at.isoformat(), json.dumps(scopes)))
            
            logger.info(f"Stored access token for client: {client_id}")
            return token_id
    
    def validate_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Validate an access token and return token info if valid."""
        with self._lock:
            access_token_hash = self._hash_secret(access_token)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT token_id, client_id, scopes, expires_at
                    FROM oauth_tokens 
                    WHERE access_token_hash = ? AND expires_at > ?
                ''', (access_token_hash, datetime.datetime.utcnow().isoformat()))
                
                token = cursor.fetchone()
                
                if not token:
                    return None
                
                return {
                    'token_id': token['token_id'],
                    'client_id': token['client_id'],
                    'scopes': json.loads(token['scopes']),
                    'expires_at': token['expires_at']
                }
    
    def store_authorization_code(self, client_id: str, redirect_uri: str, scopes: List[str], expires_in: int = 600) -> str:
        """Store an authorization code and return it."""
        with self._lock:
            auth_code = secrets.token_urlsafe(32)
            code_hash = self._hash_secret(auth_code)
            expires_at = datetime.datetime.utcnow() + timedelta(seconds=expires_in)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO oauth_auth_codes 
                    (code_hash, client_id, redirect_uri, scopes, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code_hash, client_id, redirect_uri, json.dumps(scopes), expires_at.isoformat()))
            
            logger.info(f"Stored authorization code for client: {client_id}")
            return auth_code
    
    def validate_authorization_code(self, auth_code: str, client_id: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Validate an authorization code and mark it as used."""
        with self._lock:
            code_hash = self._hash_secret(auth_code)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT code_hash, client_id, redirect_uri, scopes, expires_at, used
                    FROM oauth_auth_codes 
                    WHERE code_hash = ? AND client_id = ? AND redirect_uri = ?
                ''', (code_hash, client_id, redirect_uri))
                
                code_record = cursor.fetchone()
                
                if not code_record:
                    logger.warning(f"Authorization code not found: {client_id}")
                    return None
                
                if code_record['used']:
                    logger.warning(f"Authorization code already used: {client_id}")
                    return None
                
                if datetime.datetime.fromisoformat(code_record['expires_at']) < datetime.datetime.utcnow():
                    logger.warning(f"Authorization code expired: {client_id}")
                    return None
                
                conn.execute('UPDATE oauth_auth_codes SET used = TRUE WHERE code_hash = ?', (code_hash,))
                
                return {
                    'client_id': code_record['client_id'],
                    'redirect_uri': code_record['redirect_uri'],
                    'scopes': json.loads(code_record['scopes'])
                }
    
    def cleanup_expired_tokens(self):
        """Clean up expired tokens and authorization codes."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                now = datetime.datetime.utcnow().isoformat()
                
                cursor = conn.execute('DELETE FROM oauth_tokens WHERE expires_at < ?', (now,))
                tokens_deleted = cursor.rowcount
                
                cursor = conn.execute('DELETE FROM oauth_auth_codes WHERE expires_at < ?', (now,))
                codes_deleted = cursor.rowcount
                
                if tokens_deleted > 0 or codes_deleted > 0:
                    logger.info(f"Cleaned up {tokens_deleted} expired tokens and {codes_deleted} expired codes")


@lru_cache(maxsize=1)
def _fetch_jwks(issuer: str) -> Dict[str, Any]:
    """Download the issuer's JWKS once and keep it in memory."""
    try:
        if "api.descope.com/v1/apps/" in issuer: # specific to Descope
            project_id = issuer.split("/")[-1] 
            url = f"https://api.descope.com/{project_id}/.well-known/jwks.json"
        else:
            base_url = issuer.rstrip("/")
            url = f"{base_url}/.well-known/jwks.json"

        logger.debug(f"Fetching JWKS from: {url}")
        
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        
        jwks_data = resp.json()
        
        # validate JWKS structure
        if not isinstance(jwks_data, dict) or "keys" not in jwks_data:
            raise ValueError(f"Invalid JWKS format from {url}")
        
        if not isinstance(jwks_data["keys"], list):
            raise ValueError(f"JWKS keys must be a list from {url}")
            
        # validation of each key
        for key in jwks_data["keys"]:
            if not isinstance(key, dict) or "kty" not in key:
                raise ValueError(f"Invalid JWK format from {url}")
        
        logger.info(f"Successfully fetched {len(jwks_data['keys'])} keys from {url}")
        
        return {
            "ts": time.time(), 
            "keys": jwks_data["keys"],
            "url": url  
        }
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching JWKS from {issuer}")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching JWKS from {issuer}: {e.response.status_code}")
        raise
    except Exception as e:
        logger.error(f"Error fetching JWKS from {issuer}: {e}")
        raise

def _jwks(issuer: str, ttl_seconds: int = 600) -> List[Dict[str, Any]]:
    """Return the cached JWKS; refresh based on TTL."""
    try:
        cached = _fetch_jwks(issuer)
        
        # check if cache is stale
        if time.time() - cached["ts"] > ttl_seconds:
            logger.debug(f"JWKS cache expired for {issuer}, refreshing...")
            _fetch_jwks.cache_clear()
            cached = _fetch_jwks(issuer)
            
        return cached["keys"]
        
    except Exception as e:
        logger.error(f"Failed to get JWKS for {issuer}: {e}")
        return []

def get_jwks_for_issuer(issuer: str) -> Optional[Dict[str, Any]]:
    """Get JWKS in the standard format for an issuer."""
    try:
        keys = _jwks(issuer)
        return {"keys": keys} if keys else None
    except Exception as e:
        logger.error(f"Error getting JWKS for {issuer}: {e}")
        return None

def _parse_client_credentials(headers: Dict[str, str], form_data: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """Parse client credentials from headers or form data."""
    auth_header = headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            credentials = base64.b64decode(auth_header[6:]).decode()
            client_id, client_secret = credentials.split(":", 1)
            return client_id, client_secret
        except Exception:
            pass
    
    client_id = form_data.get("client_id")
    client_secret = form_data.get("client_secret")
    return client_id, client_secret

def _sanitize_metadata_response(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize metadata response to ensure valid well-known format."""
    required_fields = ["name", "capabilities", "schemas"]
    for field in required_fields:
        if field not in metadata:
            raise ValueError(f"Missing required field: {field}")
    
    if not isinstance(metadata["capabilities"], dict):
        raise ValueError("Capabilities must be a dictionary")
    
    if not isinstance(metadata["schemas"], dict):
        raise ValueError("Schemas must be a dictionary")
    
    if "oauth2" in metadata:
        oauth2 = metadata["oauth2"]
        if not isinstance(oauth2, dict):
            raise ValueError("OAuth2 configuration must be a dictionary")
            
        required_oauth_fields = ["authorization_endpoint", "token_endpoint", "jwks_uri"]
        for field in required_oauth_fields:
            if field not in oauth2:
                raise ValueError(f"Missing required OAuth2 field: {field}")
            
        for endpoint in ["authorization_endpoint", "token_endpoint", "jwks_uri"]:
            if endpoint in oauth2 and not oauth2[endpoint].startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL for {endpoint}: {oauth2[endpoint]}")
    
    return metadata

def _sanitize_oauth_metadata(oauth_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize OAuth2 authorization server metadata."""
    # RFC 8414
    required_fields = ["issuer", "authorization_endpoint", "token_endpoint"]
    for field in required_fields:
        if field not in oauth_metadata:
            raise ValueError(f"Missing required OAuth2 metadata field: {field}")
    
    for endpoint in ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"]:
        if endpoint in oauth_metadata and not oauth_metadata[endpoint].startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL for {endpoint}: {oauth_metadata[endpoint]}")

    return oauth_metadata

@asynccontextmanager
async def default_lifespan(server: FastMCP[LifespanResultT]) -> AsyncIterator[Any]:
    """Default lifespan context manager that does nothing.

    Args:
        server: The server instance this lifespan is managing

    Returns:
        An empty context object
    """
    yield {}


def _lifespan_wrapper(
    app: FastMCP[LifespanResultT],
    lifespan: Callable[
        [FastMCP[LifespanResultT]], AbstractAsyncContextManager[LifespanResultT]
    ],
) -> Callable[
    [LowLevelServer[LifespanResultT]], AbstractAsyncContextManager[LifespanResultT]
]:
    @asynccontextmanager
    async def wrap(
        s: LowLevelServer[LifespanResultT],
    ) -> AsyncIterator[LifespanResultT]:
        async with AsyncExitStack() as stack:
            context = await stack.enter_async_context(lifespan(app))
            yield context

    return wrap


class FastMCP(Generic[LifespanResultT]):
    def __init__(
        self,
        name: str | None = None,
        instructions: str | None = None,
        *,
        version: str | None = None,
        auth: OAuthProvider | None = None,
        middleware: list[Middleware] | None = None,
        lifespan: (
            Callable[
                [FastMCP[LifespanResultT]],
                AbstractAsyncContextManager[LifespanResultT],
            ]
            | None
        ) = None,
        tool_serializer: Callable[[Any], str] | None = None,
        cache_expiration_seconds: float | None = None,
        on_duplicate_tools: DuplicateBehavior | None = None,
        on_duplicate_resources: DuplicateBehavior | None = None,
        on_duplicate_prompts: DuplicateBehavior | None = None,
        resource_prefix_format: Literal["protocol", "path"] | None = None,
        mask_error_details: bool | None = None,
        tools: list[Tool | Callable[..., Any]] | None = None,
        dependencies: list[str] | None = None,
        include_tags: set[str] | None = None,
        exclude_tags: set[str] | None = None,
        # ---
        # ---
        # --- The following arguments are DEPRECATED ---
        # ---
        # ---
        log_level: str | None = None,
        debug: bool | None = None,
        host: str | None = None,
        port: int | None = None,
        sse_path: str | None = None,
        message_path: str | None = None,
        streamable_http_path: str | None = None,
        json_response: bool | None = None,
        stateless_http: bool | None = None,
    ):
        self.resource_prefix_format: Literal["protocol", "path"] = (
            resource_prefix_format or fastmcp.settings.resource_prefix_format
        )

        self._cache = TimedCache(
            expiration=timedelta(seconds=cache_expiration_seconds or 0)
        )
        self._additional_http_routes: list[BaseRoute] = []
        self._tool_manager = ToolManager(
            duplicate_behavior=on_duplicate_tools,
            mask_error_details=mask_error_details,
        )
        self._resource_manager = ResourceManager(
            duplicate_behavior=on_duplicate_resources,
            mask_error_details=mask_error_details,
        )
        self._prompt_manager = PromptManager(
            duplicate_behavior=on_duplicate_prompts,
            mask_error_details=mask_error_details,
        )
        self._tool_serializer = tool_serializer

        if lifespan is None:
            self._has_lifespan = False
            lifespan = default_lifespan
        else:
            self._has_lifespan = True
        self._mcp_server = LowLevelServer[LifespanResultT](
            name=name or "FastMCP",
            version=version,
            instructions=instructions,
            lifespan=_lifespan_wrapper(self, lifespan),
        )

        if auth is None and fastmcp.settings.default_auth_provider == "bearer_env":
            auth = EnvBearerAuthProvider()
        self.auth = auth

        if tools:
            for tool in tools:
                if not isinstance(tool, Tool):
                    tool = Tool.from_function(tool, serializer=self._tool_serializer)
                self.add_tool(tool)

        self.include_tags = include_tags
        self.exclude_tags = exclude_tags

        self.middleware = middleware or []

        # Set up MCP protocol handlers
        self._setup_handlers()
        self.dependencies = dependencies or fastmcp.settings.server_dependencies

        # handle deprecated settings
        self._handle_deprecated_settings(
            log_level=log_level,
            debug=debug,
            host=host,
            port=port,
            sse_path=sse_path,
            message_path=message_path,
            streamable_http_path=streamable_http_path,
            json_response=json_response,
            stateless_http=stateless_http,
        )

        self._metadata_server = None
        self._metadata_thread = None
        self._oauth_config = None
        self._oauth_storage = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"

    def _handle_deprecated_settings(
        self,
        log_level: str | None,
        debug: bool | None,
        host: str | None,
        port: int | None,
        sse_path: str | None,
        message_path: str | None,
        streamable_http_path: str | None,
        json_response: bool | None,
        stateless_http: bool | None,
    ) -> None:
        """Handle deprecated settings. Deprecated in 2.8.0."""
        deprecated_settings: dict[str, Any] = {}

        for name, arg in [
            ("log_level", log_level),
            ("debug", debug),
            ("host", host),
            ("port", port),
            ("sse_path", sse_path),
            ("message_path", message_path),
            ("streamable_http_path", streamable_http_path),
            ("json_response", json_response),
            ("stateless_http", stateless_http),
        ]:
            if arg is not None:
                # Deprecated in 2.8.0
                if fastmcp.settings.deprecation_warnings:
                    warnings.warn(
                        f"Providing `{name}` when creating a server is deprecated. Provide it when calling `run` or as a global setting instead.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                deprecated_settings[name] = arg

        combined_settings = fastmcp.settings.model_dump() | deprecated_settings
        self._deprecated_settings = Settings(**combined_settings)

    @property
    def settings(self) -> Settings:
        # Deprecated in 2.8.0
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "Accessing `.settings` on a FastMCP instance is deprecated. Use the global `fastmcp.settings` instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self._deprecated_settings

    @property
    def name(self) -> str:
        return self._mcp_server.name

    @property
    def instructions(self) -> str | None:
        return self._mcp_server.instructions

    async def run_async(
        self,
        transport: Transport | None = None,
        show_banner: bool = True,
        **transport_kwargs: Any,
    ) -> None:
        """Run the FastMCP server asynchronously.

        Args:
            transport: Transport protocol to use ("stdio", "sse", or "streamable-http")
        """
        if transport is None:
            transport = "stdio"
        if transport not in {"stdio", "http", "sse", "streamable-http"}:
            raise ValueError(f"Unknown transport: {transport}")

        if transport == "stdio":
            await self.run_stdio_async(
                show_banner=show_banner,
                **transport_kwargs,
            )
        elif transport in {"http", "sse", "streamable-http"}:
            await self.run_http_async(
                transport=transport,
                show_banner=show_banner,
                **transport_kwargs,
            )
        else:
            raise ValueError(f"Unknown transport: {transport}")

    def run(
        self,
        transport: Transport | None = None,
        show_banner: bool = True,
        **transport_kwargs: Any,
    ) -> None:
        """Run the FastMCP server. Note this is a synchronous function.

        Args:
            transport: Transport protocol to use ("stdio", "sse", or "streamable-http")
        """

        anyio.run(
            partial(
                self.run_async,
                transport,
                show_banner=show_banner,
                **transport_kwargs,
            )
        )

    def _setup_handlers(self) -> None:
        """Set up core MCP protocol handlers."""
        self._mcp_server.list_tools()(self._mcp_list_tools)
        self._mcp_server.list_resources()(self._mcp_list_resources)
        self._mcp_server.list_resource_templates()(self._mcp_list_resource_templates)
        self._mcp_server.list_prompts()(self._mcp_list_prompts)
        self._mcp_server.call_tool()(self._mcp_call_tool)
        self._mcp_server.read_resource()(self._mcp_read_resource)
        self._mcp_server.get_prompt()(self._mcp_get_prompt)

    async def _apply_middleware(
        self,
        context: MiddlewareContext[Any],
        call_next: Callable[[MiddlewareContext[Any]], Awaitable[Any]],
    ) -> Any:
        """Builds and executes the middleware chain."""
        chain = call_next
        for mw in reversed(self.middleware):
            chain = partial(mw, call_next=chain)
        return await chain(context)

    def add_middleware(self, middleware: Middleware) -> None:
        self.middleware.append(middleware)

    async def get_tools(self) -> dict[str, Tool]:
        """Get all registered tools, indexed by registered key."""
        return await self._tool_manager.get_tools()

    async def get_tool(self, key: str) -> Tool:
        tools = await self.get_tools()
        if key not in tools:
            raise NotFoundError(f"Unknown tool: {key}")
        return tools[key]

    async def get_resources(self) -> dict[str, Resource]:
        """Get all registered resources, indexed by registered key."""
        return await self._resource_manager.get_resources()

    async def get_resource(self, key: str) -> Resource:
        resources = await self.get_resources()
        if key not in resources:
            raise NotFoundError(f"Unknown resource: {key}")
        return resources[key]

    async def get_resource_templates(self) -> dict[str, ResourceTemplate]:
        """Get all registered resource templates, indexed by registered key."""
        return await self._resource_manager.get_resource_templates()

    async def get_resource_template(self, key: str) -> ResourceTemplate:
        """Get a registered resource template by key."""
        templates = await self.get_resource_templates()
        if key not in templates:
            raise NotFoundError(f"Unknown resource template: {key}")
        return templates[key]

    async def get_prompts(self) -> dict[str, Prompt]:
        """
        List all available prompts.
        """
        return await self._prompt_manager.get_prompts()

    async def get_prompt(self, key: str) -> Prompt:
        prompts = await self.get_prompts()
        if key not in prompts:
            raise NotFoundError(f"Unknown prompt: {key}")
        return prompts[key]

    def get_metadata(self) -> Dict[str, Any]:
        """Get the MCP metadata for this server."""
        
        def safe_serialize(obj):
            """Safely serialize objects to JSON-compatible format"""
            if hasattr(obj, 'model_dump'):
                return obj.model_dump(exclude_none=True)
            elif hasattr(obj, 'dict'):
                return obj.dict(exclude_none=True)
            elif hasattr(obj, '__dict__'):
                return {k: safe_serialize(v) for k, v in obj.__dict__.items() if v is not None}
            elif isinstance(obj, (list, tuple)):
                return [safe_serialize(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: safe_serialize(v) for k, v in obj.items() if v is not None}
            else:
                return obj

        # Use synchronous access to avoid event loop issues
        tool_schemas = []
        resource_schemas = []
        template_schemas = []
        prompt_schemas = []
        
        try:
            # Access managers directly to avoid async issues
            if hasattr(self, '_tool_manager') and hasattr(self._tool_manager, '_tools'):
                for name, tool in self._tool_manager._tools.items():
                    if self._should_enable_component(tool):
                        tool_info = {
                            "name": name,
                            "description": tool.description,
                            "tags": list(tool.tags) if tool.tags else [],
                        }
                        if hasattr(tool, 'input_schema'):
                            tool_info["input_schema"] = tool.input_schema
                        if hasattr(tool, 'parameters'):
                            tool_info["input_schema"] = {
                                "type": "object",
                                "properties": tool.parameters.get("properties", {}),
                                "required": tool.parameters.get("required", [])
                            }
                        tool_schemas.append(tool_info)

            if hasattr(self, '_resource_manager'):
                if hasattr(self._resource_manager, '_resources'):
                    for uri, resource in self._resource_manager._resources.items():
                        if self._should_enable_component(resource):
                            resource_schemas.append({
                                "uri": uri,
                                "name": resource.name,
                                "description": resource.description,
                                "mime_type": resource.mime_type,
                                "tags": list(resource.tags) if resource.tags else [],
                            })
                
                if hasattr(self._resource_manager, '_templates'):
                    for uri_template, template in self._resource_manager._templates.items():
                        if self._should_enable_component(template):
                            template_schemas.append({
                                "uri_template": uri_template,
                                "name": template.name,
                                "description": template.description,
                                "mime_type": template.mime_type,
                                "tags": list(template.tags) if template.tags else [],
                            })

            if hasattr(self, '_prompt_manager') and hasattr(self._prompt_manager, '_prompts'):
                for name, prompt in self._prompt_manager._prompts.items():
                    if self._should_enable_component(prompt):
                        prompt_info = {
                            "name": name,
                            "description": prompt.description,
                            "tags": list(prompt.tags) if prompt.tags else [],
                        }
                        if hasattr(prompt, 'arguments'):
                            prompt_info["arguments"] = safe_serialize(prompt.arguments)
                        prompt_schemas.append(prompt_info)

        except Exception as e:
            logger.warning(f"Error accessing managers directly: {e}")
            # If direct access fails, return basic metadata
            pass

        metadata = {
            "name": self.name,
            "version": getattr(self, '_version', "1.0.0"),
            "instructions": self.instructions,
            "capabilities": {
                "tools": len(tool_schemas),
                "resources": len(resource_schemas),
                "resource_templates": len(template_schemas),
                "prompts": len(prompt_schemas),
            },
            "schemas": {
                "tools": tool_schemas,
                "resources": resource_schemas,
                "resource_templates": template_schemas,
                "prompts": prompt_schemas,
            }
        }

        # Add OAuth2 configuration if available
        if hasattr(self, '_oauth_config') and self._oauth_config:
            base_url = self._oauth_config.get('base_url', 'http://localhost:8080')
            metadata["oauth2"] = {
                "authorization_endpoint": f"{base_url}/oauth/authorize",
                "token_endpoint": f"{base_url}/oauth/token",
                "jwks_uri": f"{base_url}/oauth/jwks",
                "scopes_supported": self._oauth_config.get("scopes_supported", ["read", "write"]),
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "client_credentials"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"]
            }
            
            if self._oauth_config.get("dynamic_registration", False):
                metadata["oauth2"]["registration_endpoint"] = f"{base_url}/oauth/register"

        metadata["server_capabilities"] = {
            "experimental": {
                "http_metadata": True,
                "oauth2_dynamic_registration": self._oauth_config.get("dynamic_registration", False) if hasattr(self, '_oauth_config') and self._oauth_config else False
            }
        }

        return _sanitize_metadata_response(metadata)        

    def start_metadata_server(
        self,
        port: int = 8080,
        host: str = "localhost",
        cors_enabled: bool = True,
        custom_headers: Optional[Dict[str, str]] = None,
        oauth_config: Optional[Dict[str, Any]] = None, 
        oauth_db_path: Optional[str] = None 
    ) -> None:
            """Start HTTP server for metadata endpoints."""
            if hasattr(self, '_metadata_server') and self._metadata_server:
                raise RuntimeError("Metadata server is already running.")

            self._oauth_config = oauth_config
            if oauth_config and 'base_url' not in oauth_config:
                oauth_config['base_url'] = f"http://{host}:{port}"
            
            if oauth_config:
                self._oauth_storage = OAuth2Storage(oauth_db_path)
            else:
                self._oauth_storage = None

            try:
                fastmcp_instance = self

                class ConfiguredMetadataHandler(BaseHTTPRequestHandler):
                    def __init__(self, request, client_address, server):
                        self.mcp_server = fastmcp_instance
                        self.cors_enabled = cors_enabled
                        self.custom_headers = custom_headers or {}
                        self.oauth_config = oauth_config
                        self.base_url = oauth_config.get('base_url', f"http://{host}:{port}") if oauth_config else f"http://{host}:{port}"
                        super().__init__(request, client_address, server)
                    
                    def do_OPTIONS(self):
                        """Handle CORS preflight requests."""
                        self.send_response(200)
                        if self.cors_enabled:
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                            self.send_header("Access-Control-Allow-Headers", "Content-Type")
                        self.end_headers()

                    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
                        """Send a JSON response with proper headers."""
                        try:
                            self.send_response(status_code)
                            self.send_header('Content-type', 'application/json')
                            
                            if self.cors_enabled:
                                self.send_header("Access-Control-Allow-Origin", "*")
                            
                            for header, value in self.custom_headers.items():
                                self.send_header(header, value)
                            
                            self.end_headers()
                            
                            response = json.dumps(data, indent=2)
                            self.wfile.write(response.encode())
                        except Exception as e:
                            logger.error(f"Error sending JSON response: {e}")
                            self.send_error(500, "Internal server error")

                    def _send_error_response(self, status_code: int, message: str):
                        """Send a standardized error response."""
                        error_response = {
                            "error": {
                                "code": status_code,
                                "message": message
                            }
                        }
                        self._send_json_response(error_response, status_code)
                    
                    def do_GET(self):
                        """Handle GET requests for metadata endpoints"""
                        try:
                            if self.path == '/.well-known/mcp-metadata':
                                self._handle_metadata()
                            elif self.path == '/.well-known/oauth-authorization-server':
                                self._handle_oauth_metadata()
                            elif self.path == '/oauth/jwks':
                                self._handle_jwks()
                            elif self.path == '/oauth/authorize':
                                self._handle_authorize()
                            else:
                                self.send_error(404, "Not Found")
                        except Exception as e:
                            logger.error(f"Error handling GET request: {e}")
                            self.send_error(500, "Internal server error")

                    def do_POST(self):
                        """Handle POST requests for OAuth2 endpoints"""
                        try:
                            if self.path == '/oauth/register':
                                self._handle_client_registration()
                            elif self.path == '/oauth/token':
                                self._handle_token_request()
                            else:
                                self.send_error(404, "Not Found")
                        except Exception as e:
                            logger.error(f"Error handling POST request: {e}")
                            self.send_error(500, "Internal server error")

                    def _handle_metadata(self):
                        """Handle MCP metadata endpoint."""
                        try:
                            metadata = self.mcp_server.get_metadata()
                            self._send_json_response(metadata)
                        except ValueError as e:
                            logger.error(f"Metadata validation error: {e}")
                            self._send_error_response(500, "Invalid metadata format")
                        except Exception as e:
                            logger.error(f"Error generating metadata: {e}")
                            self._send_error_response(500, "Error generating metadata")

                    def _handle_authorize(self):
                        """Handle OAuth2 authorization endpoint."""
                        if not self.oauth_config:
                            self.send_error(404, "OAuth2 not configured")
                            return
                        
                        # This would typically redirect to a login page or handle the authorization flow
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        
                        # Add CORS headers if enabled
                        if self.cors_enabled:
                            self.send_header("Access-Control-Allow-Origin", "*")
                    
                        # Add custom headers
                        for header, value in self.custom_headers.items():
                            self.send_header(header, value)
                        
                        self.end_headers()

                    def _handle_client_registration(self):
                        """Handle dynamic client registration (RFC 7591)."""
                        if not self.oauth_config or not self.oauth_config.get("dynamic_registration", False):
                            self._send_error_response(404, "Dynamic client registration not supported")
                            return
                        try:
                            content_length = int(self.headers.get('Content-Length', 0))
                            if content_length > 0:
                                body = self.rfile.read(content_length)
                                try:
                                    request_data = json.loads(body.decode())
                                except json.JSONDecodeError:
                                    self._send_error_response(400, "Invalid JSON in request body")
                                    return
                            else:
                                request_data = {}

                            # validate
                            if not isinstance(request_data, dict):
                                self._send_error_response(400, "Request body must be a JSON object")
                                return

                            # generate credentials
                            client_id = f"mcp-client-{secrets.token_urlsafe(16)}"
                            client_secret = secrets.token_urlsafe(32)

                            client_name = request_data.get("client_name", "MCP Client")
                            redirect_uris = request_data.get("redirect_uris", [])
                            grant_types = request_data.get("grant_types", ["authorization_code"])

                            if redirect_uris:
                                for uri in redirect_uris:
                                    if not isinstance(uri, str) or not uri.startswith(("http://", "https://")):
                                        self._send_error_response(400, f"Invalid redirect URI: {uri}")
                                        return
                            
                            supported_grant_types = ["authorization_code", "client_credentials"]
                            for grant_type in grant_types:
                                if grant_type not in supported_grant_types:
                                    self._send_error_response(400, f"Unsupported grant type: {grant_type}")
                                    return

                            registration_response = {
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "client_name": client_name,
                                "redirect_uris": redirect_uris,
                                "grant_types": grant_types,
                                "token_endpoint_auth_method": "client_secret_basic",
                                "client_secret_expires_at": 0 
                            }   
                        
                            logger.info(f"Registered new client: {client_id}")
                            self._send_json_response(registration_response, 201)
                        
                        except Exception as e:
                            logger.error(f"Error in client registration: {e}")
                            self._send_error_response(400, "Invalid registration request")

                    def _handle_token_request(self):
                        """Handle OAuth2 token endpoint with proper credential validation."""
                        if not self.oauth_config:
                            self._send_error_response(404, "OAuth2 not configured")
                            return
                        
                        try:
                            content_length = int(self.headers.get('Content-Length', 0))
                            if content_length > 0:
                                body = self.rfile.read(content_length)
                                try:
                                    form_data = urllib.parse.parse_qs(body.decode())
                                    token_request = {k: v[0] if v else None for k, v in form_data.items()}
                                except Exception:
                                    self._send_error_response(400, "Invalid form data")
                                    return
                            else:
                                token_request = {}
                            
                            grant_type = token_request.get("grant_type")
                            if not grant_type:
                                self._send_error_response(400, "Missing grant_type parameter")
                                return
                            
                            client_id, client_secret = _parse_client_credentials(
                                dict(self.headers),
                                token_request
                            )
                            
                            if not client_id or not client_secret:
                                self._send_error_response(400, "Missing client credentials")
                                return
                            
                            # Validate client credentials
                            client_info = self.oauth_storage.validate_client_credentials(client_id, client_secret)
                            if not client_info:
                                self._send_error_response(401, "Invalid client credentials")
                                return
                            
                            if grant_type == "client_credentials":
                                if "client_credentials" not in client_info['grant_types']:
                                    self._send_error_response(400, "Client not authorized for client_credentials grant")
                                    return
                                
                                # Generate access token
                                access_token = secrets.token_urlsafe(32)
                                expires_in = 3600
                                scopes = client_info.get('scopes', ['read', 'write'])
                                
                                # Store token
                                self.oauth_storage.store_access_token(client_id, access_token, expires_in, scopes)
                                
                                token_response = {
                                    "access_token": access_token,
                                    "token_type": "Bearer",
                                    "expires_in": expires_in,
                                    "scope": " ".join(scopes)
                                }
                                
                                self._send_json_response(token_response)
                                
                            elif grant_type == "authorization_code":
                                if "authorization_code" not in client_info['grant_types']:
                                    self._send_error_response(400, "Client not authorized for authorization_code grant")
                                    return
                                
                                code = token_request.get("code")
                                redirect_uri = token_request.get("redirect_uri")
                                
                                if not code:
                                    self._send_error_response(400, "Missing authorization code")
                                    return
                                
                                if not redirect_uri:
                                    self._send_error_response(400, "Missing redirect_uri")
                                    return
                                
                                # Validate authorization code
                                code_info = self.oauth_storage.validate_authorization_code(code, client_id, redirect_uri)
                                if not code_info:
                                    self._send_error_response(400, "Invalid authorization code")
                                    return
                                
                                # Generate access token
                                access_token = secrets.token_urlsafe(32)
                                expires_in = 3600
                                scopes = code_info.get('scopes', ['read', 'write'])
                                
                                # Store token
                                self.oauth_storage.store_access_token(client_id, access_token, expires_in, scopes)
                                
                                token_response = {
                                    "access_token": access_token,
                                    "token_type": "Bearer",
                                    "expires_in": expires_in,
                                    "scope": " ".join(scopes)
                                }
                                
                                self._send_json_response(token_response)
                                
                            else:
                                self._send_error_response(400, f"Unsupported grant type: {grant_type}")
                                
                        except Exception as e:
                            logger.error(f"Error in token request: {e}")
                            self._send_error_response(400, "Invalid token request")
                                

                # Create server
                self._metadata_server = HTTPServer((host, port), ConfiguredMetadataHandler)
                self._metadata_thread = threading.Thread(
                    target=self._metadata_server.serve_forever,
                    daemon=True
                )
                self._metadata_thread.start()
                
                logger.info(f"Metadata server started on http://{host}:{port}")
                logger.info(f"Metadata available at: http://{host}:{port}/.well-known/mcp-metadata")

                if oauth_config:
                    logger.info(f"OAuth2 metadata at: http://{host}:{port}/.well-known/oauth-authorization-server")
                    logger.info(f"OAuth2 endpoints:")
                    logger.info(f"  - Authorization: http://{host}:{port}/oauth/authorize")
                    logger.info(f"  - Token: http://{host}:{port}/oauth/token")
                    logger.info(f"  - JWKS: http://{host}:{port}/oauth/jwks")
                    if oauth_config.get("dynamic_registration", False):
                        logger.info(f"  - Registration: http://{host}:{port}/oauth/register")

                if cors_enabled:
                    logger.info("CORS enabled for metadata endpoints")
                
            except Exception as e:
                logger.error(f"Failed to start metadata server: {e}")
                raise

    def _periodic_cleanup(self):
        """Periodic cleanup of expired tokens and codes."""
        while True:
            try:
                if self._oauth_storage:
                    self._oauth_storage.cleanup_expired_tokens()
                time.sleep(300)  
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                time.sleep(60)
    
    def stop_metadata_server(self) -> None:
        """Stop the metadata server"""
        if hasattr(self, '_metadata_server') and self._metadata_server:
            self._metadata_server.shutdown()
            self._metadata_server = None
            if hasattr(self, '_metadata_thread'):
                self._metadata_thread.join(timeout=1)
            logger.info("Metadata server stopped")

    def custom_route(
        self,
        path: str,
        methods: list[str],
        name: str | None = None,
        include_in_schema: bool = True,
    ):
        """
        Decorator to register a custom HTTP route on the FastMCP server.

        Allows adding arbitrary HTTP endpoints outside the standard MCP protocol,
        which can be useful for OAuth callbacks, health checks, or admin APIs.
        The handler function must be an async function that accepts a Starlette
        Request and returns a Response.

        Args:
            path: URL path for the route (e.g., "/oauth/callback")
            methods: List of HTTP methods to support (e.g., ["GET", "POST"])
            name: Optional name for the route (to reference this route with
                Starlette's reverse URL lookup feature)
            include_in_schema: Whether to include in OpenAPI schema, defaults to True

        Example:
            Register a custom HTTP route for a health check endpoint:
            ```python
            @server.custom_route("/health", methods=["GET"])
            async def health_check(request: Request) -> Response:
                return JSONResponse({"status": "ok"})
            ```
        """

        def decorator(
            fn: Callable[[Request], Awaitable[Response]],
        ) -> Callable[[Request], Awaitable[Response]]:
            self._additional_http_routes.append(
                Route(
                    path,
                    endpoint=fn,
                    methods=methods,
                    name=name,
                    include_in_schema=include_in_schema,
                )
            )
            return fn

        return decorator

    async def _mcp_list_tools(self) -> list[MCPTool]:
        logger.debug("Handler called: list_tools")

        async with fastmcp.server.context.Context(fastmcp=self):
            tools = await self._list_tools()
            return [tool.to_mcp_tool(name=tool.key) for tool in tools]

    async def _list_tools(self) -> list[Tool]:
        """
        List all available tools, in the format expected by the low-level MCP
        server.
        """

        async def _handler(
            context: MiddlewareContext[mcp.types.ListToolsRequest],
        ) -> list[Tool]:
            tools = await self._tool_manager.list_tools()  # type: ignore[reportPrivateUsage]

            mcp_tools: list[Tool] = []
            for tool in tools:
                if self._should_enable_component(tool):
                    mcp_tools.append(tool)

            return mcp_tools

        async with fastmcp.server.context.Context(fastmcp=self) as fastmcp_ctx:
            # Create the middleware context.
            mw_context = MiddlewareContext(
                message=mcp.types.ListToolsRequest(method="tools/list"),
                source="client",
                type="request",
                method="tools/list",
                fastmcp_context=fastmcp_ctx,
            )

            # Apply the middleware chain.
            return await self._apply_middleware(mw_context, _handler)

    async def _mcp_list_resources(self) -> list[MCPResource]:
        logger.debug("Handler called: list_resources")

        async with fastmcp.server.context.Context(fastmcp=self):
            resources = await self._list_resources()
            return [
                resource.to_mcp_resource(uri=resource.key) for resource in resources
            ]

    async def _list_resources(self) -> list[Resource]:
        """
        List all available resources, in the format expected by the low-level MCP
        server.

        """

        async def _handler(
            context: MiddlewareContext[dict[str, Any]],
        ) -> list[Resource]:
            resources = await self._resource_manager.list_resources()  # type: ignore[reportPrivateUsage]

            mcp_resources: list[Resource] = []
            for resource in resources:
                if self._should_enable_component(resource):
                    mcp_resources.append(resource)

            return mcp_resources

        async with fastmcp.server.context.Context(fastmcp=self) as fastmcp_ctx:
            # Create the middleware context.
            mw_context = MiddlewareContext(
                message={},  # List resources doesn't have parameters
                source="client",
                type="request",
                method="resources/list",
                fastmcp_context=fastmcp_ctx,
            )

            # Apply the middleware chain.
            return await self._apply_middleware(mw_context, _handler)

    async def _mcp_list_resource_templates(self) -> list[MCPResourceTemplate]:
        logger.debug("Handler called: list_resource_templates")

        async with fastmcp.server.context.Context(fastmcp=self):
            templates = await self._list_resource_templates()
            return [
                template.to_mcp_template(uriTemplate=template.key)
                for template in templates
            ]

    async def _list_resource_templates(self) -> list[ResourceTemplate]:
        """
        List all available resource templates, in the format expected by the low-level MCP
        server.

        """

        async def _handler(
            context: MiddlewareContext[dict[str, Any]],
        ) -> list[ResourceTemplate]:
            templates = await self._resource_manager.list_resource_templates()

            mcp_templates: list[ResourceTemplate] = []
            for template in templates:
                if self._should_enable_component(template):
                    mcp_templates.append(template)

            return mcp_templates

        async with fastmcp.server.context.Context(fastmcp=self) as fastmcp_ctx:
            # Create the middleware context.
            mw_context = MiddlewareContext(
                message={},  # List resource templates doesn't have parameters
                source="client",
                type="request",
                method="resources/templates/list",
                fastmcp_context=fastmcp_ctx,
            )

            # Apply the middleware chain.
            return await self._apply_middleware(mw_context, _handler)

    async def _mcp_list_prompts(self) -> list[MCPPrompt]:
        logger.debug("Handler called: list_prompts")

        async with fastmcp.server.context.Context(fastmcp=self):
            prompts = await self._list_prompts()
            return [prompt.to_mcp_prompt(name=prompt.key) for prompt in prompts]

    async def _list_prompts(self) -> list[Prompt]:
        """
        List all available prompts, in the format expected by the low-level MCP
        server.

        """

        async def _handler(
            context: MiddlewareContext[mcp.types.ListPromptsRequest],
        ) -> list[Prompt]:
            prompts = await self._prompt_manager.list_prompts()  # type: ignore[reportPrivateUsage]

            mcp_prompts: list[Prompt] = []
            for prompt in prompts:
                if self._should_enable_component(prompt):
                    mcp_prompts.append(prompt)

            return mcp_prompts

        async with fastmcp.server.context.Context(fastmcp=self) as fastmcp_ctx:
            # Create the middleware context.
            mw_context = MiddlewareContext(
                message=mcp.types.ListPromptsRequest(method="prompts/list"),
                source="client",
                type="request",
                method="prompts/list",
                fastmcp_context=fastmcp_ctx,
            )

            # Apply the middleware chain.
            return await self._apply_middleware(mw_context, _handler)

    async def _mcp_call_tool(
        self, key: str, arguments: dict[str, Any]
    ) -> list[ContentBlock] | tuple[list[ContentBlock], dict[str, Any]]:
        """
        Handle MCP 'callTool' requests.

        Delegates to _call_tool, which should be overridden by FastMCP subclasses.

        Args:
            key: The name of the tool to call
            arguments: Arguments to pass to the tool

        Returns:
            List of MCP Content objects containing the tool results
        """
        logger.debug("Handler called: call_tool %s with %s", key, arguments)

        async with fastmcp.server.context.Context(fastmcp=self):
            try:
                result = await self._call_tool(key, arguments)
                return result.to_mcp_result()
            except DisabledError:
                raise NotFoundError(f"Unknown tool: {key}")
            except NotFoundError:
                raise NotFoundError(f"Unknown tool: {key}")

    async def _call_tool(self, key: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Applies this server's middleware and delegates the filtered call to the manager.
        """

        async def _handler(
            context: MiddlewareContext[mcp.types.CallToolRequestParams],
        ) -> ToolResult:
            tool = await self._tool_manager.get_tool(context.message.name)
            if not self._should_enable_component(tool):
                raise NotFoundError(f"Unknown tool: {context.message.name!r}")

            return await self._tool_manager.call_tool(
                key=context.message.name, arguments=context.message.arguments or {}
            )

        mw_context = MiddlewareContext(
            message=mcp.types.CallToolRequestParams(name=key, arguments=arguments),
            source="client",
            type="request",
            method="tools/call",
            fastmcp_context=fastmcp.server.dependencies.get_context(),
        )
        return await self._apply_middleware(mw_context, _handler)

    async def _mcp_read_resource(self, uri: AnyUrl | str) -> list[ReadResourceContents]:
        """
        Handle MCP 'readResource' requests.

        Delegates to _read_resource, which should be overridden by FastMCP subclasses.
        """
        logger.debug("Handler called: read_resource %s", uri)

        async with fastmcp.server.context.Context(fastmcp=self):
            try:
                return await self._read_resource(uri)
            except DisabledError:
                # convert to NotFoundError to avoid leaking resource presence
                raise NotFoundError(f"Unknown resource: {str(uri)!r}")
            except NotFoundError:
                # standardize NotFound message
                raise NotFoundError(f"Unknown resource: {str(uri)!r}")

    async def _read_resource(self, uri: AnyUrl | str) -> list[ReadResourceContents]:
        """
        Applies this server's middleware and delegates the filtered call to the manager.
        """

        async def _handler(
            context: MiddlewareContext[mcp.types.ReadResourceRequestParams],
        ) -> list[ReadResourceContents]:
            resource = await self._resource_manager.get_resource(context.message.uri)
            if not self._should_enable_component(resource):
                raise NotFoundError(f"Unknown resource: {str(context.message.uri)!r}")

            content = await self._resource_manager.read_resource(context.message.uri)
            return [
                ReadResourceContents(
                    content=content,
                    mime_type=resource.mime_type,
                )
            ]

        # Convert string URI to AnyUrl if needed
        if isinstance(uri, str):
            uri_param = AnyUrl(uri)
        else:
            uri_param = uri

        mw_context = MiddlewareContext(
            message=mcp.types.ReadResourceRequestParams(uri=uri_param),
            source="client",
            type="request",
            method="resources/read",
            fastmcp_context=fastmcp.server.dependencies.get_context(),
        )
        return await self._apply_middleware(mw_context, _handler)

    async def _mcp_get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> GetPromptResult:
        """
        Handle MCP 'getPrompt' requests.

        Delegates to _get_prompt, which should be overridden by FastMCP subclasses.
        """
        logger.debug("Handler called: get_prompt %s with %s", name, arguments)

        async with fastmcp.server.context.Context(fastmcp=self):
            try:
                return await self._get_prompt(name, arguments)
            except DisabledError:
                # convert to NotFoundError to avoid leaking prompt presence
                raise NotFoundError(f"Unknown prompt: {name}")
            except NotFoundError:
                # standardize NotFound message
                raise NotFoundError(f"Unknown prompt: {name}")

    async def _get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> GetPromptResult:
        """
        Applies this server's middleware and delegates the filtered call to the manager.
        """

        async def _handler(
            context: MiddlewareContext[mcp.types.GetPromptRequestParams],
        ) -> GetPromptResult:
            prompt = await self._prompt_manager.get_prompt(context.message.name)
            if not self._should_enable_component(prompt):
                raise NotFoundError(f"Unknown prompt: {context.message.name!r}")

            return await self._prompt_manager.render_prompt(
                name=context.message.name, arguments=context.message.arguments
            )

        mw_context = MiddlewareContext(
            message=mcp.types.GetPromptRequestParams(name=name, arguments=arguments),
            source="client",
            type="request",
            method="prompts/get",
            fastmcp_context=fastmcp.server.dependencies.get_context(),
        )
        return await self._apply_middleware(mw_context, _handler)

    def add_tool(self, tool: Tool) -> Tool:
        """Add a tool to the server.

        The tool function can optionally request a Context object by adding a parameter
        with the Context type annotation. See the @tool decorator for examples.

        Args:
            tool: The Tool instance to register

        Returns:
            The tool instance that was added to the server.
        """
        self._tool_manager.add_tool(tool)
        self._cache.clear()

        # Send notification if we're in a request context
        try:
            from fastmcp.server.dependencies import get_context

            context = get_context()
            context._queue_tool_list_changed()  # type: ignore[private-use]
        except RuntimeError:
            pass  # No context available

        return tool

    def remove_tool(self, name: str) -> None:
        """Remove a tool from the server.

        Args:
            name: The name of the tool to remove

        Raises:
            NotFoundError: If the tool is not found
        """
        self._tool_manager.remove_tool(name)
        self._cache.clear()

        # Send notification if we're in a request context
        try:
            from fastmcp.server.dependencies import get_context

            context = get_context()
            context._queue_tool_list_changed()  # type: ignore[private-use]
        except RuntimeError:
            pass  # No context available

    @overload
    def tool(
        self,
        name_or_fn: AnyFunction,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        output_schema: dict[str, Any] | None | NotSetT = NotSet,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        exclude_args: list[str] | None = None,
        enabled: bool | None = None,
    ) -> FunctionTool: ...

    @overload
    def tool(
        self,
        name_or_fn: str | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        output_schema: dict[str, Any] | None | NotSetT = NotSet,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        exclude_args: list[str] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], FunctionTool]: ...

    def tool(
        self,
        name_or_fn: str | AnyFunction | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        output_schema: dict[str, Any] | None | NotSetT = NotSet,
        annotations: ToolAnnotations | dict[str, Any] | None = None,
        exclude_args: list[str] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], FunctionTool] | FunctionTool:
        """Decorator to register a tool.

        Tools can optionally request a Context object by adding a parameter with the
        Context type annotation. The context provides access to MCP capabilities like
        logging, progress reporting, and resource access.

        This decorator supports multiple calling patterns:
        - @server.tool (without parentheses)
        - @server.tool (with empty parentheses)
        - @server.tool("custom_name") (with name as first argument)
        - @server.tool(name="custom_name") (with name as keyword argument)
        - server.tool(function, name="custom_name") (direct function call)

        Args:
            name_or_fn: Either a function (when used as @tool), a string name, or None
            name: Optional name for the tool (keyword-only, alternative to name_or_fn)
            description: Optional description of what the tool does
            tags: Optional set of tags for categorizing the tool
            output_schema: Optional JSON schema for the tool's output
            annotations: Optional annotations about the tool's behavior
            exclude_args: Optional list of argument names to exclude from the tool schema
            enabled: Optional boolean to enable or disable the tool

        Examples:
            Register a tool with a custom name:
            ```python
            @server.tool
            def my_tool(x: int) -> str:
                return str(x)

            # Register a tool with a custom name
            @server.tool
            def my_tool(x: int) -> str:
                return str(x)

            @server.tool("custom_name")
            def my_tool(x: int) -> str:
                return str(x)

            @server.tool(name="custom_name")
            def my_tool(x: int) -> str:
                return str(x)

            # Direct function call
            server.tool(my_function, name="custom_name")
            ```
        """
        if isinstance(annotations, dict):
            annotations = ToolAnnotations(**annotations)

        if isinstance(name_or_fn, classmethod):
            raise ValueError(
                inspect.cleandoc(
                    """
                    To decorate a classmethod, first define the method and then call
                    tool() directly on the method instead of using it as a
                    decorator. See https://gofastmcp.com/patterns/decorating-methods
                    for examples and more information.
                    """
                )
            )

        # Determine the actual name and function based on the calling pattern
        if inspect.isroutine(name_or_fn):
            # Case 1: @tool (without parens) - function passed directly
            # Case 2: direct call like tool(fn, name="something")
            fn = name_or_fn
            tool_name = name  # Use keyword name if provided, otherwise None

            # Register the tool immediately and return the tool object
            tool = Tool.from_function(
                fn,
                name=tool_name,
                title=title,
                description=description,
                tags=tags,
                output_schema=output_schema,
                annotations=annotations,
                exclude_args=exclude_args,
                serializer=self._tool_serializer,
                enabled=enabled,
            )
            self.add_tool(tool)
            return tool

        elif isinstance(name_or_fn, str):
            # Case 3: @tool("custom_name") - name passed as first argument
            if name is not None:
                raise TypeError(
                    "Cannot specify both a name as first argument and as keyword argument. "
                    f"Use either @tool('{name_or_fn}') or @tool(name='{name}'), not both."
                )
            tool_name = name_or_fn
        elif name_or_fn is None:
            # Case 4: @tool or @tool(name="something") - use keyword name
            tool_name = name
        else:
            raise TypeError(
                f"First argument to @tool must be a function, string, or None, got {type(name_or_fn)}"
            )

        # Return partial for cases where we need to wait for the function
        return partial(
            self.tool,
            name=tool_name,
            title=title,
            description=description,
            tags=tags,
            output_schema=output_schema,
            annotations=annotations,
            exclude_args=exclude_args,
            enabled=enabled,
        )

    def add_resource(self, resource: Resource) -> Resource:
        """Add a resource to the server.

        Args:
            resource: A Resource instance to add

        Returns:
            The resource instance that was added to the server.
        """
        self._resource_manager.add_resource(resource)
        self._cache.clear()

        # Send notification if we're in a request context
        try:
            from fastmcp.server.dependencies import get_context

            context = get_context()
            context._queue_resource_list_changed()  # type: ignore[private-use]
        except RuntimeError:
            pass  # No context available

        return resource

    def add_template(self, template: ResourceTemplate) -> ResourceTemplate:
        """Add a resource template to the server.

        Args:
            template: A ResourceTemplate instance to add

        Returns:
            The template instance that was added to the server.
        """
        self._resource_manager.add_template(template)

        # Send notification if we're in a request context
        try:
            from fastmcp.server.dependencies import get_context

            context = get_context()
            context._queue_resource_list_changed()  # type: ignore[private-use]
        except RuntimeError:
            pass  # No context available

        return template

    def add_resource_fn(
        self,
        fn: AnyFunction,
        uri: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        tags: set[str] | None = None,
    ) -> None:
        """Add a resource or template to the server from a function.

        If the URI contains parameters (e.g. "resource://{param}") or the function
        has parameters, it will be registered as a template resource.

        Args:
            fn: The function to register as a resource
            uri: The URI for the resource
            name: Optional name for the resource
            description: Optional description of the resource
            mime_type: Optional MIME type for the resource
            tags: Optional set of tags for categorizing the resource
        """
        # deprecated since 2.7.0
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "The add_resource_fn method is deprecated. Use the resource decorator instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._resource_manager.add_resource_or_template_from_fn(
            fn=fn,
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
            tags=tags,
        )
        self._cache.clear()

    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        tags: set[str] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], Resource | ResourceTemplate]:
        """Decorator to register a function as a resource.

        The function will be called when the resource is read to generate its content.
        The function can return:
        - str for text content
        - bytes for binary content
        - other types will be converted to JSON

        Resources can optionally request a Context object by adding a parameter with the
        Context type annotation. The context provides access to MCP capabilities like
        logging, progress reporting, and session information.

        If the URI contains parameters (e.g. "resource://{param}") or the function
        has parameters, it will be registered as a template resource.

        Args:
            uri: URI for the resource (e.g. "resource://my-resource" or "resource://{param}")
            name: Optional name for the resource
            description: Optional description of the resource
            mime_type: Optional MIME type for the resource
            tags: Optional set of tags for categorizing the resource
            enabled: Optional boolean to enable or disable the resource

        Examples:
            Register a resource with a custom name:
            ```python
            @server.resource("resource://my-resource")
            def get_data() -> str:
                return "Hello, world!"

            @server.resource("resource://my-resource")
            async get_data() -> str:
                data = await fetch_data()
                return f"Hello, world! {data}"

            @server.resource("resource://{city}/weather")
            def get_weather(city: str) -> str:
                return f"Weather for {city}"

            @server.resource("resource://{city}/weather")
            def get_weather_with_context(city: str, ctx: Context) -> str:
                ctx.info(f"Fetching weather for {city}")
                return f"Weather for {city}"

            @server.resource("resource://{city}/weather")
            async def get_weather(city: str) -> str:
                data = await fetch_weather(city)
                return f"Weather for {city}: {data}"
            ```
        """
        # Check if user passed function directly instead of calling decorator
        if inspect.isroutine(uri):
            raise TypeError(
                "The @resource decorator was used incorrectly. "
                "Did you forget to call it? Use @resource('uri') instead of @resource"
            )

        def decorator(fn: AnyFunction) -> Resource | ResourceTemplate:
            from fastmcp.server.context import Context

            if isinstance(fn, classmethod):  # type: ignore[reportUnnecessaryIsInstance]
                raise ValueError(
                    inspect.cleandoc(
                        """
                        To decorate a classmethod, first define the method and then call
                        resource() directly on the method instead of using it as a
                        decorator. See https://gofastmcp.com/patterns/decorating-methods
                        for examples and more information.
                        """
                    )
                )

            # Check if this should be a template
            has_uri_params = "{" in uri and "}" in uri
            # check if the function has any parameters (other than injected context)
            has_func_params = any(
                p
                for p in inspect.signature(fn).parameters.values()
                if p.annotation is not Context
            )

            if has_uri_params or has_func_params:
                template = ResourceTemplate.from_function(
                    fn=fn,
                    uri_template=uri,
                    name=name,
                    title=title,
                    description=description,
                    mime_type=mime_type,
                    tags=tags,
                    enabled=enabled,
                )
                self.add_template(template)
                return template
            elif not has_uri_params and not has_func_params:
                resource = Resource.from_function(
                    fn=fn,
                    uri=uri,
                    name=name,
                    title=title,
                    description=description,
                    mime_type=mime_type,
                    tags=tags,
                    enabled=enabled,
                )
                self.add_resource(resource)
                return resource
            else:
                raise ValueError(
                    "Invalid resource or template definition due to a "
                    "mismatch between URI parameters and function parameters."
                )

        return decorator

    def add_prompt(self, prompt: Prompt) -> Prompt:
        """Add a prompt to the server.

        Args:
            prompt: A Prompt instance to add

        Returns:
            The prompt instance that was added to the server.
        """
        self._prompt_manager.add_prompt(prompt)
        self._cache.clear()

        # Send notification if we're in a request context
        try:
            from fastmcp.server.dependencies import get_context

            context = get_context()
            context._queue_prompt_list_changed()  # type: ignore[private-use]
        except RuntimeError:
            pass  # No context available

        return prompt

    @overload
    def prompt(
        self,
        name_or_fn: AnyFunction,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        enabled: bool | None = None,
    ) -> FunctionPrompt: ...

    @overload
    def prompt(
        self,
        name_or_fn: str | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], FunctionPrompt]: ...

    def prompt(
        self,
        name_or_fn: str | AnyFunction | None = None,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: set[str] | None = None,
        enabled: bool | None = None,
    ) -> Callable[[AnyFunction], FunctionPrompt] | FunctionPrompt:
        """Decorator to register a prompt.

        Prompts can optionally request a Context object by adding a parameter with the
        Context type annotation. The context provides access to MCP capabilities like
        logging, progress reporting, and session information.

        This decorator supports multiple calling patterns:
        - @server.prompt (without parentheses)
        - @server.prompt() (with empty parentheses)
        - @server.prompt("custom_name") (with name as first argument)
        - @server.prompt(name="custom_name") (with name as keyword argument)
        - server.prompt(function, name="custom_name") (direct function call)

        Args:
            name_or_fn: Either a function (when used as @prompt), a string name, or None
            name: Optional name for the prompt (keyword-only, alternative to name_or_fn)
            description: Optional description of what the prompt does
            tags: Optional set of tags for categorizing the prompt
            enabled: Optional boolean to enable or disable the prompt

        Examples:

            ```python
            @server.prompt
            def analyze_table(table_name: str) -> list[Message]:
                schema = read_table_schema(table_name)
                return [
                    {
                        "role": "user",
                        "content": f"Analyze this schema:\n{schema}"
                    }
                ]

            @server.prompt()
            def analyze_with_context(table_name: str, ctx: Context) -> list[Message]:
                ctx.info(f"Analyzing table {table_name}")
                schema = read_table_schema(table_name)
                return [
                    {
                        "role": "user",
                        "content": f"Analyze this schema:\n{schema}"
                    }
                ]

            @server.prompt("custom_name")
            def analyze_file(path: str) -> list[Message]:
                content = await read_file(path)
                return [
                    {
                        "role": "user",
                        "content": {
                            "type": "resource",
                            "resource": {
                                "uri": f"file://{path}",
                                "text": content
                            }
                        }
                    }
                ]

            @server.prompt(name="custom_name")
            def another_prompt(data: str) -> list[Message]:
                return [{"role": "user", "content": data}]

            # Direct function call
            server.prompt(my_function, name="custom_name")
            ```
        """

        if isinstance(name_or_fn, classmethod):
            raise ValueError(
                inspect.cleandoc(
                    """
                    To decorate a classmethod, first define the method and then call
                    prompt() directly on the method instead of using it as a
                    decorator. See https://gofastmcp.com/patterns/decorating-methods
                    for examples and more information.
                    """
                )
            )

        # Determine the actual name and function based on the calling pattern
        if inspect.isroutine(name_or_fn):
            # Case 1: @prompt (without parens) - function passed directly as decorator
            # Case 2: direct call like prompt(fn, name="something")
            fn = name_or_fn
            prompt_name = name  # Use keyword name if provided, otherwise None

            # Register the prompt immediately
            prompt = Prompt.from_function(
                fn=fn,
                name=prompt_name,
                title=title,
                description=description,
                tags=tags,
                enabled=enabled,
            )
            self.add_prompt(prompt)

            return prompt

        elif isinstance(name_or_fn, str):
            # Case 3: @prompt("custom_name") - name passed as first argument
            if name is not None:
                raise TypeError(
                    "Cannot specify both a name as first argument and as keyword argument. "
                    f"Use either @prompt('{name_or_fn}') or @prompt(name='{name}'), not both."
                )
            prompt_name = name_or_fn
        elif name_or_fn is None:
            # Case 4: @prompt() or @prompt(name="something") - use keyword name
            prompt_name = name
        else:
            raise TypeError(
                f"First argument to @prompt must be a function, string, or None, got {type(name_or_fn)}"
            )

        # Return partial for cases where we need to wait for the function
        return partial(
            self.prompt,
            name=prompt_name,
            title=title,
            description=description,
            tags=tags,
            enabled=enabled,
        )

    async def run_stdio_async(self, show_banner: bool = True) -> None:
        """Run the server using stdio transport."""

        # Display server banner
        if show_banner:
            log_server_banner(
                server=self,
                transport="stdio",
            )

        async with stdio_server() as (read_stream, write_stream):
            logger.info(f"Starting MCP server {self.name!r} with transport 'stdio'")
            await self._mcp_server.run(
                read_stream,
                write_stream,
                self._mcp_server.create_initialization_options(
                    NotificationOptions(tools_changed=True)
                ),
            )

    async def run_http_async(
        self,
        show_banner: bool = True,
        transport: Literal["http", "streamable-http", "sse"] = "http",
        host: str | None = None,
        port: int | None = None,
        log_level: str | None = None,
        path: str | None = None,
        uvicorn_config: dict[str, Any] | None = None,
        middleware: list[ASGIMiddleware] | None = None,
        stateless_http: bool | None = None,
    ) -> None:
        """Run the server using HTTP transport.

        Args:
            transport: Transport protocol to use - either "streamable-http" (default) or "sse"
            host: Host address to bind to (defaults to settings.host)
            port: Port to bind to (defaults to settings.port)
            log_level: Log level for the server (defaults to settings.log_level)
            path: Path for the endpoint (defaults to settings.streamable_http_path or settings.sse_path)
            uvicorn_config: Additional configuration for the Uvicorn server
            middleware: A list of middleware to apply to the app
            stateless_http: Whether to use stateless HTTP (defaults to settings.stateless_http)
        """

        host = host or self._deprecated_settings.host
        port = port or self._deprecated_settings.port
        default_log_level_to_use = (
            log_level or self._deprecated_settings.log_level
        ).lower()

        app = self.http_app(
            path=path,
            transport=transport,
            middleware=middleware,
            stateless_http=stateless_http,
        )

        # Get the path for the server URL
        server_path = (
            app.state.path.lstrip("/")
            if hasattr(app, "state") and hasattr(app.state, "path")
            else path or ""
        )

        # Display server banner
        if show_banner:
            log_server_banner(
                server=self,
                transport=transport,
                host=host,
                port=port,
                path=server_path,
            )
        _uvicorn_config_from_user = uvicorn_config or {}

        config_kwargs: dict[str, Any] = {
            "timeout_graceful_shutdown": 0,
            "lifespan": "on",
        }
        config_kwargs.update(_uvicorn_config_from_user)

        if "log_config" not in config_kwargs and "log_level" not in config_kwargs:
            config_kwargs["log_level"] = default_log_level_to_use

        config = uvicorn.Config(app, host=host, port=port, **config_kwargs)
        server = uvicorn.Server(config)
        path = app.state.path.lstrip("/")  # type: ignore
        logger.info(
            f"Starting MCP server {self.name!r} with transport {transport!r} on http://{host}:{port}/{path}"
        )

        await server.serve()

    async def run_sse_async(
        self,
        host: str | None = None,
        port: int | None = None,
        log_level: str | None = None,
        path: str | None = None,
        uvicorn_config: dict[str, Any] | None = None,
    ) -> None:
        """Run the server using SSE transport."""

        # Deprecated since 2.3.2
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "The run_sse_async method is deprecated (as of 2.3.2). Use run_http_async for a "
                "modern (non-SSE) alternative, or create an SSE app with "
                "`fastmcp.server.http.create_sse_app` and run it directly.",
                DeprecationWarning,
                stacklevel=2,
            )
        await self.run_http_async(
            transport="sse",
            host=host,
            port=port,
            log_level=log_level,
            path=path,
            uvicorn_config=uvicorn_config,
        )

    def sse_app(
        self,
        path: str | None = None,
        message_path: str | None = None,
        middleware: list[ASGIMiddleware] | None = None,
    ) -> StarletteWithLifespan:
        """
        Create a Starlette app for the SSE server.

        Args:
            path: The path to the SSE endpoint
            message_path: The path to the message endpoint
            middleware: A list of middleware to apply to the app
        """
        # Deprecated since 2.3.2
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "The sse_app method is deprecated (as of 2.3.2). Use http_app as a modern (non-SSE) "
                "alternative, or call `fastmcp.server.http.create_sse_app` directly.",
                DeprecationWarning,
                stacklevel=2,
            )
        return create_sse_app(
            server=self,
            message_path=message_path or self._deprecated_settings.message_path,
            sse_path=path or self._deprecated_settings.sse_path,
            auth=self.auth,
            debug=self._deprecated_settings.debug,
            middleware=middleware,
        )

    def streamable_http_app(
        self,
        path: str | None = None,
        middleware: list[ASGIMiddleware] | None = None,
    ) -> StarletteWithLifespan:
        """
        Create a Starlette app for the StreamableHTTP server.

        Args:
            path: The path to the StreamableHTTP endpoint
            middleware: A list of middleware to apply to the app
        """
        # Deprecated since 2.3.2
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "The streamable_http_app method is deprecated (as of 2.3.2). Use http_app() instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        return self.http_app(path=path, middleware=middleware)

    def http_app(
        self,
        path: str | None = None,
        middleware: list[ASGIMiddleware] | None = None,
        json_response: bool | None = None,
        stateless_http: bool | None = None,
        transport: Literal["http", "streamable-http", "sse"] = "http",
    ) -> StarletteWithLifespan:
        """Create a Starlette app using the specified HTTP transport.

        Args:
            path: The path for the HTTP endpoint
            middleware: A list of middleware to apply to the app
            transport: Transport protocol to use - either "streamable-http" (default) or "sse"

        Returns:
            A Starlette application configured with the specified transport
        """

        if transport in ("streamable-http", "http"):
            return create_streamable_http_app(
                server=self,
                streamable_http_path=path
                or self._deprecated_settings.streamable_http_path,
                event_store=None,
                auth=self.auth,
                json_response=(
                    json_response
                    if json_response is not None
                    else self._deprecated_settings.json_response
                ),
                stateless_http=(
                    stateless_http
                    if stateless_http is not None
                    else self._deprecated_settings.stateless_http
                ),
                debug=self._deprecated_settings.debug,
                middleware=middleware,
            )
        elif transport == "sse":
            return create_sse_app(
                server=self,
                message_path=self._deprecated_settings.message_path,
                sse_path=path or self._deprecated_settings.sse_path,
                auth=self.auth,
                debug=self._deprecated_settings.debug,
                middleware=middleware,
            )

    async def run_streamable_http_async(
        self,
        host: str | None = None,
        port: int | None = None,
        log_level: str | None = None,
        path: str | None = None,
        uvicorn_config: dict[str, Any] | None = None,
    ) -> None:
        # Deprecated since 2.3.2
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "The run_streamable_http_async method is deprecated (as of 2.3.2). "
                "Use run_http_async instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        await self.run_http_async(
            transport="http",
            host=host,
            port=port,
            log_level=log_level,
            path=path,
            uvicorn_config=uvicorn_config,
        )

    def mount(
        self,
        server: FastMCP[LifespanResultT],
        prefix: str | None = None,
        as_proxy: bool | None = None,
        *,
        tool_separator: str | None = None,
        resource_separator: str | None = None,
        prompt_separator: str | None = None,
    ) -> None:
        """Mount another FastMCP server on this server with an optional prefix.

        Unlike importing (with import_server), mounting establishes a dynamic connection
        between servers. When a client interacts with a mounted server's objects through
        the parent server, requests are forwarded to the mounted server in real-time.
        This means changes to the mounted server are immediately reflected when accessed
        through the parent.

        When a server is mounted with a prefix:
        - Tools from the mounted server are accessible with prefixed names.
          Example: If server has a tool named "get_weather", it will be available as "prefix_get_weather".
        - Resources are accessible with prefixed URIs.
          Example: If server has a resource with URI "weather://forecast", it will be available as
          "weather://prefix/forecast".
        - Templates are accessible with prefixed URI templates.
          Example: If server has a template with URI "weather://location/{id}", it will be available
          as "weather://prefix/location/{id}".
        - Prompts are accessible with prefixed names.
          Example: If server has a prompt named "weather_prompt", it will be available as
          "prefix_weather_prompt".

        When a server is mounted without a prefix (prefix=None), its tools, resources, templates,
        and prompts are accessible with their original names. Multiple servers can be mounted
        without prefixes, and they will be tried in order until a match is found.

        There are two modes for mounting servers:
        1. Direct mounting (default when server has no custom lifespan): The parent server
           directly accesses the mounted server's objects in-memory for better performance.
           In this mode, no client lifecycle events occur on the mounted server, including
           lifespan execution.

        2. Proxy mounting (default when server has a custom lifespan): The parent server
           treats the mounted server as a separate entity and communicates with it via a
           Client transport. This preserves all client-facing behaviors, including lifespan
           execution, but with slightly higher overhead.

        Args:
            server: The FastMCP server to mount.
            prefix: Optional prefix to use for the mounted server's objects. If None,
                the server's objects are accessible with their original names.
            as_proxy: Whether to treat the mounted server as a proxy. If None (default),
                automatically determined based on whether the server has a custom lifespan
                (True if it has a custom lifespan, False otherwise).
            tool_separator: Deprecated. Separator character for tool names.
            resource_separator: Deprecated. Separator character for resource URIs.
            prompt_separator: Deprecated. Separator character for prompt names.
        """
        from fastmcp.client.transports import FastMCPTransport
        from fastmcp.server.proxy import FastMCPProxy, ProxyClient

        # Deprecated since 2.9.0
        # Prior to 2.9.0, the first positional argument was the prefix and the
        # second was the server. Here we swap them if needed now that the prefix
        # is optional.
        if isinstance(server, str):
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "Mount prefixes are now optional and the first positional argument "
                    "should be the server you want to mount.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            server, prefix = cast(FastMCP[Any], prefix), server

        if tool_separator is not None:
            # Deprecated since 2.4.0
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "The tool_separator parameter is deprecated and will be removed in a future version. "
                    "Tools are now prefixed using 'prefix_toolname' format.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        if resource_separator is not None:
            # Deprecated since 2.4.0
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "The resource_separator parameter is deprecated and ignored. "
                    "Resource prefixes are now added using the protocol://prefix/path format.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        if prompt_separator is not None:
            # Deprecated since 2.4.0
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "The prompt_separator parameter is deprecated and will be removed in a future version. "
                    "Prompts are now prefixed using 'prefix_promptname' format.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        # if as_proxy is not specified and the server has a custom lifespan,
        # we should treat it as a proxy
        if as_proxy is None:
            as_proxy = server._has_lifespan

        if as_proxy and not isinstance(server, FastMCPProxy):
            server = FastMCPProxy(ProxyClient(transport=FastMCPTransport(server)))

        # Delegate mounting to all three managers
        mounted_server = MountedServer(
            prefix=prefix,
            server=server,
            resource_prefix_format=self.resource_prefix_format,
        )
        self._tool_manager.mount(mounted_server)
        self._resource_manager.mount(mounted_server)
        self._prompt_manager.mount(mounted_server)

        self._cache.clear()

    async def import_server(
        self,
        server: FastMCP[LifespanResultT],
        prefix: str | None = None,
        tool_separator: str | None = None,
        resource_separator: str | None = None,
        prompt_separator: str | None = None,
    ) -> None:
        """
        Import the MCP objects from another FastMCP server into this one,
        optionally with a given prefix.

        Note that when a server is *imported*, its objects are immediately
        registered to the importing server. This is a one-time operation and
        future changes to the imported server will not be reflected in the
        importing server. Server-level configurations and lifespans are not imported.

        When a server is imported with a prefix:
        - The tools are imported with prefixed names
          Example: If server has a tool named "get_weather", it will be
          available as "prefix_get_weather"
        - The resources are imported with prefixed URIs using the new format
          Example: If server has a resource with URI "weather://forecast", it will
          be available as "weather://prefix/forecast"
        - The templates are imported with prefixed URI templates using the new format
          Example: If server has a template with URI "weather://location/{id}", it will
          be available as "weather://prefix/location/{id}"
        - The prompts are imported with prefixed names
          Example: If server has a prompt named "weather_prompt", it will be available as
          "prefix_weather_prompt"

        When a server is imported without a prefix (prefix=None), its tools, resources,
        templates, and prompts are imported with their original names.

        Args:
            server: The FastMCP server to import
            prefix: Optional prefix to use for the imported server's objects. If None,
                objects are imported with their original names.
            tool_separator: Deprecated. Separator for tool names.
            resource_separator: Deprecated and ignored. Prefix is now
              applied using the protocol://prefix/path format
            prompt_separator: Deprecated. Separator for prompt names.
        """

        # Deprecated since 2.9.0
        # Prior to 2.9.0, the first positional argument was the prefix and the
        # second was the server. Here we swap them if needed now that the prefix
        # is optional.
        if isinstance(server, str):
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "Import prefixes are now optional and the first positional argument "
                    "should be the server you want to import.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            server, prefix = cast(FastMCP[Any], prefix), server

        if tool_separator is not None:
            # Deprecated since 2.4.0
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "The tool_separator parameter is deprecated and will be removed in a future version. "
                    "Tools are now prefixed using 'prefix_toolname' format.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        if resource_separator is not None:
            # Deprecated since 2.4.0
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "The resource_separator parameter is deprecated and ignored. "
                    "Resource prefixes are now added using the protocol://prefix/path format.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        if prompt_separator is not None:
            # Deprecated since 2.4.0
            if fastmcp.settings.deprecation_warnings:
                warnings.warn(
                    "The prompt_separator parameter is deprecated and will be removed in a future version. "
                    "Prompts are now prefixed using 'prefix_promptname' format.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        # Import tools from the server
        for key, tool in (await server.get_tools()).items():
            if prefix:
                tool = tool.with_key(f"{prefix}_{key}")
            self._tool_manager.add_tool(tool)

        # Import resources and templates from the server
        for key, resource in (await server.get_resources()).items():
            if prefix:
                resource_key = add_resource_prefix(
                    key, prefix, self.resource_prefix_format
                )
                resource = resource.with_key(resource_key)
            self._resource_manager.add_resource(resource)

        for key, template in (await server.get_resource_templates()).items():
            if prefix:
                template_key = add_resource_prefix(
                    key, prefix, self.resource_prefix_format
                )
                template = template.with_key(template_key)
            self._resource_manager.add_template(template)

        # Import prompts from the server
        for key, prompt in (await server.get_prompts()).items():
            if prefix:
                prompt = prompt.with_key(f"{prefix}_{key}")
            self._prompt_manager.add_prompt(prompt)

        if prefix:
            logger.debug(f"Imported server {server.name} with prefix '{prefix}'")
        else:
            logger.debug(f"Imported server {server.name}")

        self._cache.clear()

    @classmethod
    def from_openapi(
        cls,
        openapi_spec: dict[str, Any],
        client: httpx.AsyncClient,
        route_maps: list[RouteMap] | None = None,
        route_map_fn: OpenAPIRouteMapFn | None = None,
        mcp_component_fn: OpenAPIComponentFn | None = None,
        mcp_names: dict[str, str] | None = None,
        tags: set[str] | None = None,
        **settings: Any,
    ) -> FastMCPOpenAPI:
        """
        Create a FastMCP server from an OpenAPI specification.
        """
        from .openapi import FastMCPOpenAPI

        return FastMCPOpenAPI(
            openapi_spec=openapi_spec,
            client=client,
            route_maps=route_maps,
            route_map_fn=route_map_fn,
            mcp_component_fn=mcp_component_fn,
            mcp_names=mcp_names,
            tags=tags,
            **settings,
        )

    @classmethod
    def from_fastapi(
        cls,
        app: Any,
        name: str | None = None,
        route_maps: list[RouteMap] | None = None,
        route_map_fn: OpenAPIRouteMapFn | None = None,
        mcp_component_fn: OpenAPIComponentFn | None = None,
        mcp_names: dict[str, str] | None = None,
        httpx_client_kwargs: dict[str, Any] | None = None,
        tags: set[str] | None = None,
        **settings: Any,
    ) -> FastMCPOpenAPI:
        """
        Create a FastMCP server from a FastAPI application.
        """

        from .openapi import FastMCPOpenAPI

        if httpx_client_kwargs is None:
            httpx_client_kwargs = {}
        httpx_client_kwargs.setdefault("base_url", "http://fastapi")

        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            **httpx_client_kwargs,
        )

        name = name or app.title

        return FastMCPOpenAPI(
            openapi_spec=app.openapi(),
            client=client,
            name=name,
            route_maps=route_maps,
            route_map_fn=route_map_fn,
            mcp_component_fn=mcp_component_fn,
            mcp_names=mcp_names,
            tags=tags,
            **settings,
        )

    @classmethod
    def as_proxy(
        cls,
        backend: (
            Client[ClientTransportT]
            | ClientTransport
            | FastMCP[Any]
            | AnyUrl
            | Path
            | MCPConfig
            | dict[str, Any]
            | str
        ),
        **settings: Any,
    ) -> FastMCPProxy:
        """Create a FastMCP proxy server for the given backend.

        The `backend` argument can be either an existing `fastmcp.client.Client`
        instance or any value accepted as the `transport` argument of
        `fastmcp.client.Client`. This mirrors the convenience of the
        `fastmcp.client.Client` constructor.
        """
        from fastmcp.client.client import Client
        from fastmcp.server.proxy import FastMCPProxy, ProxyClient

        if isinstance(backend, Client):
            client = backend
            # Session strategy based on client connection state:
            # - Connected clients: reuse existing session for all requests
            # - Disconnected clients: create fresh sessions per request for isolation
            if client.is_connected():
                from fastmcp.utilities.logging import get_logger

                logger = get_logger(__name__)
                logger.info(
                    "Proxy detected connected client - reusing existing session for all requests. "
                    "This may cause context mixing in concurrent scenarios."
                )

                # Reuse sessions - return the same client instance
                def reuse_client_factory():
                    return client

                client_factory = reuse_client_factory
            else:
                # Fresh sessions per request
                def fresh_client_factory():
                    return client.new()

                client_factory = fresh_client_factory
        else:
            base_client = ProxyClient(backend)

            # Fresh client created from transport - use fresh sessions per request
            def proxy_client_factory():
                return base_client.new()

            client_factory = proxy_client_factory

        return FastMCPProxy(client_factory=client_factory, **settings)

    @classmethod
    def from_client(
        cls, client: Client[ClientTransportT], **settings: Any
    ) -> FastMCPProxy:
        """
        Create a FastMCP proxy server from a FastMCP client.
        """
        # Deprecated since 2.3.5
        if fastmcp.settings.deprecation_warnings:
            warnings.warn(
                "FastMCP.from_client() is deprecated; use FastMCP.as_proxy() instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        return cls.as_proxy(client, **settings)

    def _should_enable_component(
        self,
        component: FastMCPComponent,
    ) -> bool:
        """
        Given a component, determine if it should be enabled. Returns True if it should be enabled; False if it should not.

        Rules:
            - If the component's enabled property is False, always return False.
            - If both include_tags and exclude_tags are None, return True.
            - If exclude_tags is provided, check each exclude tag:
                - If the exclude tag is a string, it must be present in the input tags to exclude.
            - If include_tags is provided, check each include tag:
                - If the include tag is a string, it must be present in the input tags to include.
            - If include_tags is provided and none of the include tags match, return False.
            - If include_tags is not provided, return True.
        """
        if not component.enabled:
            return False

        if self.include_tags is None and self.exclude_tags is None:
            return True

        if self.exclude_tags is not None:
            if any(etag in component.tags for etag in self.exclude_tags):
                return False

        if self.include_tags is not None:
            if any(itag in component.tags for itag in self.include_tags):
                return True
            else:
                return False

        return True


@dataclass
class MountedServer:
    prefix: str | None
    server: FastMCP[Any]
    resource_prefix_format: Literal["protocol", "path"] | None = None


def add_resource_prefix(
    uri: str, prefix: str, prefix_format: Literal["protocol", "path"] | None = None
) -> str:
    """Add a prefix to a resource URI.

    Args:
        uri: The original resource URI
        prefix: The prefix to add

    Returns:
        The resource URI with the prefix added

    Examples:
        With new style:
        ```python
        add_resource_prefix("resource://path/to/resource", "prefix")
        "resource://prefix/path/to/resource"
        ```
        With legacy style:
        ```python
        add_resource_prefix("resource://path/to/resource", "prefix")
        "prefix+resource://path/to/resource"
        ```
        With absolute path:
        ```python
        add_resource_prefix("resource:///absolute/path", "prefix")
        "resource://prefix//absolute/path"
        ```

    Raises:
        ValueError: If the URI doesn't match the expected protocol://path format
    """
    if not prefix:
        return uri

    # Get the server settings to check for legacy format preference

    if prefix_format is None:
        prefix_format = fastmcp.settings.resource_prefix_format

    if prefix_format == "protocol":
        # Legacy style: prefix+protocol://path
        return f"{prefix}+{uri}"
    elif prefix_format == "path":
        # New style: protocol://prefix/path
        # Split the URI into protocol and path
        match = URI_PATTERN.match(uri)
        if not match:
            raise ValueError(
                f"Invalid URI format: {uri}. Expected protocol://path format."
            )

        protocol, path = match.groups()

        # Add the prefix to the path
        return f"{protocol}{prefix}/{path}"
    else:
        raise ValueError(f"Invalid prefix format: {prefix_format}")


def remove_resource_prefix(
    uri: str, prefix: str, prefix_format: Literal["protocol", "path"] | None = None
) -> str:
    """Remove a prefix from a resource URI.

    Args:
        uri: The resource URI with a prefix
        prefix: The prefix to remove
        prefix_format: The format of the prefix to remove
    Returns:
        The resource URI with the prefix removed

    Examples:
        With new style:
        ```python
        remove_resource_prefix("resource://prefix/path/to/resource", "prefix")
        "resource://path/to/resource"
        ```
        With legacy style:
        ```python
        remove_resource_prefix("prefix+resource://path/to/resource", "prefix")
        "resource://path/to/resource"
        ```
        With absolute path:
        ```python
        remove_resource_prefix("resource://prefix//absolute/path", "prefix")
        "resource:///absolute/path"
        ```

    Raises:
        ValueError: If the URI doesn't match the expected protocol://path format
    """
    if not prefix:
        return uri

    if prefix_format is None:
        prefix_format = fastmcp.settings.resource_prefix_format

    if prefix_format == "protocol":
        # Legacy style: prefix+protocol://path
        legacy_prefix = f"{prefix}+"
        if uri.startswith(legacy_prefix):
            return uri[len(legacy_prefix) :]
        return uri
    elif prefix_format == "path":
        # New style: protocol://prefix/path
        # Split the URI into protocol and path
        match = URI_PATTERN.match(uri)
        if not match:
            raise ValueError(
                f"Invalid URI format: {uri}. Expected protocol://path format."
            )

        protocol, path = match.groups()

        # Check if the path starts with the prefix followed by a /
        prefix_pattern = f"^{re.escape(prefix)}/(.*?)$"
        path_match = re.match(prefix_pattern, path)
        if not path_match:
            return uri

        # Return the URI without the prefix
        return f"{protocol}{path_match.group(1)}"
    else:
        raise ValueError(f"Invalid prefix format: {prefix_format}")


def has_resource_prefix(
    uri: str, prefix: str, prefix_format: Literal["protocol", "path"] | None = None
) -> bool:
    """Check if a resource URI has a specific prefix.

    Args:
        uri: The resource URI to check
        prefix: The prefix to look for

    Returns:
        True if the URI has the specified prefix, False otherwise

    Examples:
        With new style:
        ```python
        has_resource_prefix("resource://prefix/path/to/resource", "prefix")
        True
        ```
        With legacy style:
        ```python
        has_resource_prefix("prefix+resource://path/to/resource", "prefix")
        True
        ```
        With other path:
        ```python
        has_resource_prefix("resource://other/path/to/resource", "prefix")
        False
        ```

    Raises:
        ValueError: If the URI doesn't match the expected protocol://path format
    """
    if not prefix:
        return False

    # Get the server settings to check for legacy format preference

    if prefix_format is None:
        prefix_format = fastmcp.settings.resource_prefix_format

    if prefix_format == "protocol":
        # Legacy style: prefix+protocol://path
        legacy_prefix = f"{prefix}+"
        return uri.startswith(legacy_prefix)
    elif prefix_format == "path":
        # New style: protocol://prefix/path
        # Split the URI into protocol and path
        match = URI_PATTERN.match(uri)
        if not match:
            raise ValueError(
                f"Invalid URI format: {uri}. Expected protocol://path format."
            )

        _, path = match.groups()

        # Check if the path starts with the prefix followed by a /
        prefix_pattern = f"^{re.escape(prefix)}/"
        return bool(re.match(prefix_pattern, path))
    else:
        raise ValueError(f"Invalid prefix format: {prefix_format}")
