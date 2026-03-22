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
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).parent
_CONFIG_YAML = _PKG_DIR / "config.yaml"
_DOT_ENV = _PKG_DIR / ".env"


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


class AccountConfig(BaseModel):
    id: str
    label: str = ""
    imap: ImapConfig
    smtp: SmtpConfig
    username_env: str
    password_env: str
    default: bool = False
    # Resolved at runtime — populated after secret resolution
    username: str = Field(default="", exclude=True)
    password: str = Field(default="", exclude=True)


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
