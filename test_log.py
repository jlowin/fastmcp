import logging
from fastmcp import FastMCP
from contextlib import asynccontextmanager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastMCP):  # noqa: ANN201, ARG001
    """Application lifespan handler"""
    logger.info("Starting MCP API...")
    yield
    logger.info("Closing MCP API...")


mcp = FastMCP(
    name="MCP",
    host="0.0.0.0",
    port=8050,
    stateless_http=True,
    lifespan=lifespan,
)

mcp.run(transport="streamable-http", show_banner=False, log_level="INFO")
