from ssl import VerifyMode

from fastmcp.client.transports import StreamableHttpTransport
import httpx

async def test_oauth_uses_same_client_as_transport():
    transport = StreamableHttpTransport(
        "https://some.fake.url/",
        httpx_client_factory=lambda *args, **kwargs: httpx.AsyncClient(verify=False, *args, **kwargs),
        auth="oauth",
    )

    async with transport.auth.httpx_client_factory() as httpx_client:
        assert httpx_client._transport._pool._ssl_context.verify_mode == VerifyMode.CERT_NONE
