"""Unit tests for config loading (no network required)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from mail_mcp.config import (
    SecretsUnavailableError,
    get_config,
    get_default_account,
)


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear the lru_cache between tests."""
    from mail_mcp import config as cfg_module
    cfg_module.get_config.cache_clear()
    yield
    cfg_module.get_config.cache_clear()


def test_config_loads():
    config = get_config()
    assert len(config.accounts) > 0


def test_default_account_exists():
    with patch.dict(os.environ, {"X_LOGIN": "test_user", "X_PASS": "test_pass"}):
        acc = get_default_account()
        assert acc is not None
        assert acc.id == "poly"
        assert acc.imap.host == "webmail.polytechnique.fr"
        assert acc.imap.port == 993
        assert acc.imap.tls is True
        assert acc.smtp.port == 587
        assert acc.smtp.starttls is True


def test_secret_resolved_from_env():
    with patch.dict(os.environ, {"X_LOGIN": "test_user", "X_PASS": "test_pass"}):
        acc = get_default_account()
        assert acc.username == "test_user"
        assert acc.password == "test_pass"


def test_mcp_settings_defaults():
    config = get_config()
    assert config.mcp.default_page_size == 20
    assert config.mcp.thread_depth_limit == 50


def test_secrets_unavailable_error_raised():
    """When secret is absent from all tiers, SecretsUnavailableError must be raised."""
    config = get_config()
    # Patch zsh to return empty so login-shell tier also fails
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the key from env if present
            env_backup = os.environ.pop("X_LOGIN", None)
            try:
                with pytest.raises(SecretsUnavailableError):
                    config.get_secret("X_LOGIN", required=True)
            finally:
                if env_backup is not None:
                    os.environ["X_LOGIN"] = env_backup


def test_get_secret_optional_returns_empty():
    config = get_config()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        env_backup = os.environ.pop("NONEXISTENT_VAR_XYZ", None)
        try:
            result = config.get_secret("NONEXISTENT_VAR_XYZ", required=False)
            assert result == ""
        finally:
            if env_backup is not None:
                os.environ["NONEXISTENT_VAR_XYZ"] = env_backup
