"""
Shared administrative service layer for mail-mcp.

This module is the single backend for:
  - mail-admin (CLI)
  - HTTP admin routes (/admin/*)
  - future admin flows
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from ..config import (
    ADMIN_ENV_PATH,
    HTTP_FALLBACK_BASE_URL,
    HTTP_MCP_PATH,
    HTTP_PORT,
    HTTP_PUBLIC_BASE_URL,
    _resolve_env,
    get_config,
)


# ---------------------------------------------------------------------------
# Log setup
# ---------------------------------------------------------------------------

_LOG_DIR = ADMIN_ENV_PATH.parent / "logs"
_LOG_FILE = _LOG_DIR / "mail_admin_debug.log"


class _FlushingFileHandler(logging.FileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def _setup_logger() -> logging.Logger:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("mail_mcp.admin")
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        handler = _FlushingFileHandler(_LOG_FILE, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
        log.addHandler(handler)
    return log


_log = _setup_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask(value: str | None, *, show: int = 4) -> str:
    if not value:
        return "not set"
    if len(value) <= show * 2:
        return "*" * len(value)
    return f"{value[:show]}…{value[-show:]}"


def _mask_password(value: str | None) -> str:
    if not value:
        return "not set"
    return "hidden"


def _dotenv_values() -> dict[str, str]:
    return dotenv_values(ADMIN_ENV_PATH) if ADMIN_ENV_PATH.exists() else {}


def _write_env(key: str, value: str) -> None:
    ADMIN_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_ENV_PATH.touch(exist_ok=True)
    success, _, _ = set_key(str(ADMIN_ENV_PATH), key, value, quote_mode="never")
    if not success:
        raise RuntimeError(f"Failed to write {key} to {ADMIN_ENV_PATH}")


def _unset_env(key: str) -> None:
    _write_env(key, "")


def _resolve_credential(key: str) -> tuple[str | None, str]:
    """Resolve a credential, returning (value, source) with explicit source tracking."""
    # Admin .env file (highest priority inside the admin surface)
    env_file_vals = _dotenv_values()
    v = env_file_vals.get(key)
    if v:
        return v, "admin .env file"

    # Process environment (injected at container startup from deploy/.env)
    v = os.environ.get(key)
    if v:
        return v, "process environment"

    # Login shell fallback (bw-env / ~/.kshrc)
    v = _resolve_env(key)
    if v:
        return v, "login shell (zsh -l)"

    return None, "missing"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_accounts_status() -> list[dict]:
    """Return credential resolution status for all configured accounts."""
    config = get_config()
    result = []
    for account in config.accounts:
        login_val, login_source = _resolve_credential(account.username_env)
        pass_val, pass_source = _resolve_credential(account.password_env)
        result.append({
            "id": account.id,
            "label": account.label,
            "email": account.email,
            "imap": f"{account.imap.host}:{account.imap.port}",
            "smtp": f"{account.smtp.host}:{account.smtp.port}",
            "default": account.default,
            "login_env": account.username_env,
            "login_present": bool(login_val),
            "login_masked": _mask(login_val),
            "login_source": login_source,
            "password_env": account.password_env,
            "password_present": bool(pass_val),
            "password_masked": _mask_password(pass_val),
            "password_source": pass_source,
        })
    return result


# ---------------------------------------------------------------------------
# Credential management
# ---------------------------------------------------------------------------


def set_account_credentials(account_id: str, login: str, password: str) -> dict:
    """Write login + password for an account to the admin env file."""
    config = get_config()
    for account in config.accounts:
        if account.id == account_id:
            _write_env(account.username_env, login.strip())
            _write_env(account.password_env, password)
            _log.info("Credentials set for account %s (login_env=%s)", account_id, account.username_env)
            return {
                "account_id": account_id,
                "login_env": account.username_env,
                "password_env": account.password_env,
                "login_masked": _mask(login),
                "password_masked": _mask_password(password),
                "env_path": str(ADMIN_ENV_PATH),
            }
    raise ValueError(f"Account not found: {account_id!r}")


def unset_account_credentials(account_id: str) -> dict:
    """Clear login + password for an account from the admin env file."""
    config = get_config()
    for account in config.accounts:
        if account.id == account_id:
            _unset_env(account.username_env)
            _unset_env(account.password_env)
            _log.info("Credentials cleared for account %s", account_id)
            return {
                "account_id": account_id,
                "login_env": account.username_env,
                "password_env": account.password_env,
                "env_path": str(ADMIN_ENV_PATH),
            }
    raise ValueError(f"Account not found: {account_id!r}")


# ---------------------------------------------------------------------------
# Log access
# ---------------------------------------------------------------------------


def get_logs_text(lines: int = 50) -> str:
    if not _LOG_FILE.exists():
        return "No admin log file yet."
    chunk = _LOG_FILE.read_text(encoding="utf-8").splitlines()[-max(1, lines):]
    return "\n".join(chunk) if chunk else "No admin log lines available."


# ---------------------------------------------------------------------------
# Help and status text (shared across all surfaces)
# ---------------------------------------------------------------------------


def admin_help_text() -> str:
    return "\n".join([
        "mail-admin capabilities",
        "- CLI:",
        "  - mail-admin status [--account ACCOUNT_ID]",
        "  - mail-admin help",
        "  - mail-admin logs [N]",
        "  - mail-admin credentials set --account ACCOUNT_ID --login LOGIN --password PASS",
        "  - mail-admin credentials unset --account ACCOUNT_ID",
        "- HTTP:",
        "  - GET /health",
        "  - GET /admin/status",
        "  - GET /admin/help",
        "  - GET /admin/logs?lines=40",
        "  - POST /admin/credentials/set  body: {account_id, login, password}",
        "  - POST /admin/credentials/unset  body: {account_id}",
        "- SSH (inside container):",
        "  - docker compose exec -T mail-mcp mail-admin status",
        "  - docker compose logs --tail=100 mail-mcp",
    ])


def status_summary_text() -> str:
    accounts = get_accounts_status()
    lines = ["mail-admin status", f"- admin env path: {ADMIN_ENV_PATH}"]
    for a in accounts:
        default_marker = " [default]" if a["default"] else ""
        lines.append(f"- account: {a['id']} ({a['label']}){default_marker}")
        lines.append(f"  {a['login_env']}: {'set' if a['login_present'] else 'missing'} ({a['login_masked']}) [{a['login_source']}]")
        lines.append(f"  {a['password_env']}: {'set' if a['password_present'] else 'missing'} ({a['password_masked']}) [{a['password_source']}]")
    return "\n".join(lines)


def health_summary() -> str:
    return "\n".join([
        "mail-mcp health",
        f"- public: {HTTP_PUBLIC_BASE_URL}",
        f"- fallback: {HTTP_FALLBACK_BASE_URL}",
        f"- mcp: {HTTP_PUBLIC_BASE_URL}{HTTP_MCP_PATH}",
        f"- local port: {HTTP_PORT}",
    ])
