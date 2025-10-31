from ssl import VerifyMode

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
import httpx

async def test_oauth_uses_same_client_as_transport():
    transport = StreamableHttpTransport(
        "https://some.fake.url/",
        httpx_client_factory=lambda *args, **kwargs: httpx.AsyncClient(verify=False, *args, **kwargs),
        auth="oauth",
    )
    client = Client(transport=transport)

    httpx_client = transport.auth.httpx_client_factory()

    assert httpx_client._transport._pool._ssl_context.verify_mode == ssl.VerifyMode.CERT_NONE
