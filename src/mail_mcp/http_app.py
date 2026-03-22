"""HTTP surface for mail-mcp.

Exposes:
  /health        — readiness probe
  /admin/status  — operator metadata
  /mcp           — streamable HTTP MCP transport (FastMCP)
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from starlette.responses import JSONResponse
from starlette.routing import Route

from .config import (
    HTTP_FALLBACK_BASE_URL,
    HTTP_MCP_PATH,
    HTTP_PORT,
    HTTP_PUBLIC_BASE_URL,
)
from .server import mcp


def _app_version() -> str:
    try:
        return pkg_version("mail-mcp")
    except PackageNotFoundError:
        return "0.2.0"


def _base_payload() -> dict:
    return {
        "ok": True,
        "product": "mail-mcp",
        "service": "IMAP+SMTP MCP transport bridge",
        "version": _app_version(),
        "transport": "streamable-http",
        "mcp_path": HTTP_MCP_PATH,
        "public_base_url": HTTP_PUBLIC_BASE_URL,
        "fallback_base_url": HTTP_FALLBACK_BASE_URL,
        "listen_port": HTTP_PORT,
    }


async def health(_request) -> JSONResponse:
    return JSONResponse(_base_payload())


async def admin_status(_request) -> JSONResponse:
    payload = _base_payload()
    payload["routes"] = {
        "health": "/health",
        "admin_status": "/admin/status",
        "mcp": HTTP_MCP_PATH,
    }
    payload["admin"] = {
        "ssh_admin": {
            "supported": True,
            "examples": [
                "docker compose exec -T mail-mcp mail-mcp status --account poly",
                "docker compose logs --tail=100 mail-mcp",
            ],
        },
    }
    return JSONResponse(payload)


app = mcp.http_app()
app.router.routes.insert(0, Route("/health", health))
app.router.routes.insert(1, Route("/admin/status", admin_status))
