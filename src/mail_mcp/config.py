"""Configuration loader for mail-mcp — canonical KpihX pattern.

Resolution tiers (priority order — last wins):
  1. Hardcoded defaults (in AccountConfig / McpSettings)
  2. config.yaml  — non-sensitive settings (hosts, ports, env var names)
  3. .env file    — local dev secret overrides (load_dotenv, never committed)
  4. os.environ   — process env (explicit exports, terminal session)
  5. zsh -l -c    — bw-env login-shell injection (GLOBAL_ENV_VARS in Bitwarden)

Tiers 4 and 5 are applied by `_resolve_env()` for every secret at access time.
Tier 3 is loaded at init via `load_dotenv(override=False)` so os.environ always wins.
"""

from __future__ import annotations

import copy
import logging
import os
import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values, load_dotenv
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).parent
_CONFIG_YAML = _PKG_DIR / "config.yaml"
_DOT_ENV = _PKG_DIR / ".env"

# ---------------------------------------------------------------------------
# Package version
# ---------------------------------------------------------------------------

def _package_version(default: str = "0.2.0") -> str:
    try:
        return pkg_version("mail-mcp")
    except PackageNotFoundError:
        return default

APP_VERSION: str = _package_version()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SecretsUnavailableError(RuntimeError):
    """Raised when a required secret cannot be resolved from any source."""


# ---------------------------------------------------------------------------
# Pydantic models (YAML-only, no secrets)
# ---------------------------------------------------------------------------


class ImapConfig(BaseModel):
    host: str
    port: int = 993
    tls: bool = True


class SmtpConfig(BaseModel):
    host: str
    port: int = 587
    starttls: bool = True


class SignatureConfig(BaseModel):
    before_logo: str = ""
    logo_path: str = ""    # relative to package dir (e.g. "assets/signature_logo.png")
    after_logo: str = ""


class AccountConfig(BaseModel):
    id: str
    label: str = ""
    imap: ImapConfig
    smtp: SmtpConfig
    username_env: str
    password_env: str
    email: str = ""              # full address for From header & SMTP envelope (e.g. user@domain.com)
    display_name: str = ""       # human name shown in From header
    signature: SignatureConfig = Field(default_factory=SignatureConfig)
    default: bool = False
    # Resolved at runtime — populated after secret resolution
    username: str = Field(default="", exclude=True)
    password: str = Field(default="", exclude=True)

    @property
    def from_address(self) -> str:
        """Return the SMTP envelope address: email if set, else username."""
        return self.email or self.username


class McpSettings(BaseModel):
    default_page_size: int = 20
    max_attachment_preview_bytes: int = 4096
    thread_depth_limit: int = 50


class _RawConfig(BaseModel):
    """Internal — direct mapping of config.yaml structure."""
    accounts: list[AccountConfig]
    mcp: McpSettings = Field(default_factory=McpSettings)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        logger.debug("Config file not found, using defaults: %s", path)
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _resolve_env(name: str) -> str | None:
    """Two-tier secret resolution.

    Tier 1: os.environ — already set (terminal session, explicit export, .env loaded by init)
    Tier 2: zsh -l -c  — bw-env secrets injected via ~/.kshrc at login time

    Returns None if the secret is absent in both tiers.
    """
    # Tier 1: process environment (.env already loaded into it via load_dotenv)
    value = os.environ.get(name)
    if value:
        return value

    # Tier 2: login shell — bw-env injects at login via ~/.kshrc
    try:
        result = subprocess.run(
            ["zsh", "-l", "-c", f'printf "%s" "${{{name}}}"'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = result.stdout.strip()
        if value:
            logger.debug("Secret '%s' resolved via login shell.", name)
            return value
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("Login shell resolution failed for '%s': %s", name, exc)

    return None


# ---------------------------------------------------------------------------
# Config class
# ---------------------------------------------------------------------------


class MailMcpConfig:
    """Layered configuration singleton for mail-mcp.

    Load order:
      1. config.yaml   (non-sensitive settings)
      2. .env file     (load_dotenv — local dev overrides, override=False → os.environ wins)
      3. os.environ    (explicit exports, bw-env injected via login shell)
    """

    def __init__(self) -> None:
        # Load .env into os.environ (override=False — process env takes priority)
        load_dotenv(_DOT_ENV, override=False)

        raw = _load_yaml(_CONFIG_YAML)
        self._raw = _RawConfig(**raw)

    @property
    def accounts(self) -> list[AccountConfig]:
        return self._raw.accounts

    @property
    def mcp(self) -> McpSettings:
        return self._raw.mcp

    def get_secret(self, name: str, *, required: bool = True) -> str:
        """Resolve a secret by name via the two-tier strategy.

        Args:
            name:     Env var name (e.g. "X_LOGIN").
            required: If True, raises SecretsUnavailableError when absent.

        Returns:
            The secret value as a string.

        Raises:
            SecretsUnavailableError: If required=True and the secret is absent.
        """
        value = _resolve_env(name)
        if value:
            return value
        if required:
            raise SecretsUnavailableError(
                f"Secret '{name}' is not available. "
                f"Ensure bw-env is unlocked or set it in {_DOT_ENV}."
            )
        return ""

    def resolve_account_secrets(self, account: AccountConfig) -> AccountConfig:
        """Populate username/password fields on an AccountConfig via secret resolution."""
        account.username = self.get_secret(account.username_env)
        account.password = self.get_secret(account.password_env)
        return account


# ---------------------------------------------------------------------------
# Cached singleton
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Admin env file — persistent credential overrides (Docker: /data/mail-admin.env)
# ---------------------------------------------------------------------------

# Env var name — allows overriding admin env file path at runtime
ENV_ADMIN_ENV_FILE: str = "MAIL_MCP_ADMIN_ENV_FILE"
_DEFAULT_ADMIN_ENV: Path = Path("~/.mcps/mail/mail-admin.env").expanduser()
ADMIN_ENV_PATH: Path = Path(
    os.environ.get(ENV_ADMIN_ENV_FILE, str(_DEFAULT_ADMIN_ENV))
).expanduser()


def _load_nonempty_dotenv(path: Path) -> None:
    """Load .env values into os.environ, silently ignoring blank placeholders.

    This ensures real admin-set credentials override the deployment env without
    allowing empty placeholder lines to clobber existing inherited secrets.
    """
    if not path.exists():
        return
    for key, value in dotenv_values(path).items():
        if value not in (None, ""):
            os.environ[key] = value


# Load admin env at startup — non-empty values take priority over deploy .env
_load_nonempty_dotenv(ADMIN_ENV_PATH)


# ---------------------------------------------------------------------------
# Telegram admin constants
# ---------------------------------------------------------------------------

ENV_TELEGRAM_MAIL_HOMELAB_TOKEN: str = "TELEGRAM_MAIL_HOMELAB_TOKEN"
ENV_TELEGRAM_CHAT_IDS: str = "TELEGRAM_CHAT_IDS"

TELEGRAM_MAIL_HOMELAB_TOKEN: str | None = os.environ.get(ENV_TELEGRAM_MAIL_HOMELAB_TOKEN)
_TELEGRAM_CHAT_IDS_RAW: str = os.environ.get(ENV_TELEGRAM_CHAT_IDS, "")
TELEGRAM_CHAT_IDS: tuple[str, ...] = tuple(
    cid.strip() for cid in _TELEGRAM_CHAT_IDS_RAW.split(",") if cid.strip()
)


# ---------------------------------------------------------------------------
# HTTP transport constants (for serve-http mode)
# ---------------------------------------------------------------------------

HTTP_HOST: str = os.environ.get("MAIL_MCP_HTTP_HOST", "0.0.0.0")
HTTP_PORT: int = int(os.environ.get("MAIL_MCP_HTTP_PORT", "8094"))
HTTP_MCP_PATH: str = os.environ.get("MAIL_MCP_HTTP_MCP_PATH", "/mcp")
HTTP_PUBLIC_BASE_URL: str = os.environ.get("MAIL_MCP_PUBLIC_BASE_URL", "https://mail.kpihx-labs.com")
HTTP_FALLBACK_BASE_URL: str = os.environ.get("MAIL_MCP_FALLBACK_BASE_URL", "https://mail.homelab")


@lru_cache(maxsize=1)
def get_config() -> MailMcpConfig:
    """Return the cached MailMcpConfig singleton."""
    return MailMcpConfig()


def get_default_account() -> AccountConfig:
    config = get_config()
    for account in config.accounts:
        if account.default:
            return config.resolve_account_secrets(account)
    if config.accounts:
        return config.resolve_account_secrets(config.accounts[0])
    raise RuntimeError("No accounts configured in config.yaml")


def get_account(account_id: str) -> AccountConfig:
    config = get_config()
    for account in config.accounts:
        if account.id == account_id:
            return config.resolve_account_secrets(account)
    raise ValueError(f"Account not found: {account_id!r}")
