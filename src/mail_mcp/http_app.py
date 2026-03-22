"""HTTP surface for mail-mcp.

Exposes:
  /health                    — readiness probe (auth presence check)
  /admin/status              — operator metadata + credential status
  /admin/help                — full capability map for CLI, HTTP, SSH
  /admin/logs?lines=40       — tail of the admin log file
  /admin/credentials/set     — POST: set IMAP/SMTP credentials for an account
  /admin/credentials/unset   — POST: clear credentials for an account
  /mcp                       — streamable HTTP MCP transport (FastMCP)
"""
from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.routing import Route

from .admin.service import (
    admin_help_text,
    get_accounts_status,
    get_logs_text,
    set_account_credentials,
    status_summary_text,
    unset_account_credentials,
)
from .config import (
    ADMIN_ENV_PATH,
    APP_VERSION,
    HTTP_FALLBACK_BASE_URL,
    HTTP_MCP_PATH,
    HTTP_PORT,
    HTTP_PUBLIC_BASE_URL,
)
from .server import mcp


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _base_payload() -> dict:
    return {
        "ok": True,
        "product": "mail-mcp",
        "service": "IMAP+SMTP MCP transport bridge",
        "version": APP_VERSION,
        "transport": "streamable-http",
        "mcp_path": HTTP_MCP_PATH,
        "public_base_url": HTTP_PUBLIC_BASE_URL,
        "fallback_base_url": HTTP_FALLBACK_BASE_URL,
        "listen_port": HTTP_PORT,
    }


def _auth_probe_payload() -> dict:
    """Non-secret credential presence check for health/status probes."""
    return {
        "accounts": [
            {
                "id": a["id"],
                "label": a["label"],
                "login_present": a["login_present"],
                "password_present": a["password_present"],
                "ready": a["login_present"] and a["password_present"],
            }
            for a in get_accounts_status()
        ]
    }


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def health(_request) -> JSONResponse:
    payload = _base_payload()
    payload["auth"] = _auth_probe_payload()
    return JSONResponse(payload)


async def admin_status(_request) -> JSONResponse:
    payload = _base_payload()
    payload["admin"] = {
        "ssh_admin": {
            "supported": True,
            "examples": [
                "docker compose exec -T mail-mcp mail-admin status",
                "docker compose logs --tail=100 mail-mcp",
            ],
        },
        "auth_probe": _auth_probe_payload(),
        "status_summary": status_summary_text(),
        "admin_env_path": str(ADMIN_ENV_PATH),
    }
    payload["routes"] = {
        "health": "/health",
        "admin_status": "/admin/status",
        "admin_help": "/admin/help",
        "admin_logs": "/admin/logs?lines=40",
        "mcp": HTTP_MCP_PATH,
    }
    return JSONResponse(payload)


async def admin_help(_request) -> JSONResponse:
    payload = _base_payload()
    payload["help"] = {
        "text": admin_help_text(),
        "routes": {
            "health": "/health",
            "admin_status": "/admin/status",
            "admin_help": "/admin/help",
            "admin_logs": "/admin/logs?lines=40",
            "credentials_set": "POST /admin/credentials/set",
            "credentials_unset": "POST /admin/credentials/unset",
            "mcp": HTTP_MCP_PATH,
        },
    }
    return JSONResponse(payload)


async def admin_logs(request) -> JSONResponse:
    lines = int(request.query_params.get("lines", "40"))
    return JSONResponse({"text": get_logs_text(lines), "lines": lines})


async def admin_credentials_set(request) -> JSONResponse:
    body = await request.json()
    account_id = body.get("account_id", "poly")
    login = body.get("login", "")
    password = body.get("password", "")
    if not login or not password:
        return JSONResponse(
            {"ok": False, "error": "Missing 'login' or 'password' in request body."},
            status_code=400,
        )
    try:
        result = set_account_credentials(account_id, login, password)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True, "action": "credentials.set", **result})


async def admin_credentials_unset(request) -> JSONResponse:
    body = await request.json()
    account_id = body.get("account_id", "poly")
    try:
        result = unset_account_credentials(account_id)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    return JSONResponse({"ok": True, "action": "credentials.unset", **result})


# ---------------------------------------------------------------------------
# App assembly
# ---------------------------------------------------------------------------

app = mcp.http_app()
app.router.routes.insert(0, Route("/health", health))
app.router.routes.insert(1, Route("/admin/status", admin_status))
app.router.routes.insert(2, Route("/admin/help", admin_help))
app.router.routes.insert(3, Route("/admin/logs", admin_logs))
app.router.routes.insert(4, Route("/admin/credentials/set", admin_credentials_set, methods=["POST"]))
app.router.routes.insert(5, Route("/admin/credentials/unset", admin_credentials_unset, methods=["POST"]))
