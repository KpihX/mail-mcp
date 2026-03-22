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

mcp.mount(guide_mcp, prefix="")
mcp.mount(read_mcp, prefix="")
mcp.mount(compose_mcp, prefix="")
mcp.mount(manage_mcp, prefix="")


def serve() -> None:
    """Entry point for `mail-mcp serve` (used by MCP host configs)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    serve()
