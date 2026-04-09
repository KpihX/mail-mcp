"""Package version alignment and mail_guide content (no network)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_app_version_matches_pyproject():
    from mail_mcp.config import APP_VERSION

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert APP_VERSION == data["project"]["version"]


def test_mail_mcp___version___matches_app_version():
    import mail_mcp

    from mail_mcp.config import APP_VERSION

    assert mail_mcp.__version__ == APP_VERSION


def test_mail_guide_includes_version_and_compose_fields(monkeypatch):
    from mail_mcp.config import APP_VERSION
    from mail_mcp.tools import guide as guide_mod

    fake_cfg = SimpleNamespace(
        accounts=[SimpleNamespace(id="poly", label="Test", default=True)]
    )
    monkeypatch.setattr(guide_mod, "get_config", lambda: fake_cfg)
    text = guide_mod.mail_guide()
    assert APP_VERSION in text
    assert "verify_bounce_window_seconds" in text
    assert "delivery_status" in text
    assert "smtp_accepted" in text
    assert "stdio" in text.lower() and "http" in text.lower()
