"""mail-mcp FastMCP server — registers all tool modules and starts the server."""

from __future__ import annotations

from fastmcp import FastMCP

from mail_mcp.tools.compose import mcp as compose_mcp
from mail_mcp.tools.guide import mcp as guide_mcp
from mail_mcp.tools.manage import mcp as manage_mcp
from mail_mcp.tools.read import mcp as read_mcp

# Root server — compose all sub-MCPs
mcp = FastMCP(
    "mail-mcp",
    instructions=(
        "Generic IMAP+SMTP MCP for email access. "
        "Call mail_guide() first to orient yourself. "
        "All tools accept an optional account_id parameter."
    ),
)

mcp.mount(guide_mcp, namespace=None)
mcp.mount(read_mcp, namespace=None)
mcp.mount(compose_mcp, namespace=None)
mcp.mount(manage_mcp, namespace=None)


def serve() -> None:
    """Entry point for `mail-mcp serve` — stdio transport."""
    mcp.run(transport="stdio")


def serve_http() -> None:
    """Entry point for `mail-mcp serve-http` — streamable HTTP transport."""
    import uvicorn
    from mail_mcp.config import HTTP_HOST, HTTP_PORT
    from mail_mcp.http_app import app as http_app
    uvicorn.run(http_app, host=HTTP_HOST, port=HTTP_PORT, reload=False)


if __name__ == "__main__":
    serve()
