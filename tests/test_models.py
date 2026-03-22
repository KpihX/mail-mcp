"""Unit tests for domain models."""

from __future__ import annotations

from mail_mcp.core.models import Address, Flag, Folder, Message, MessageSummary


def test_address_model():
    addr = Address(name="KpihX", email="x@polytechnique.edu")
    assert addr.name == "KpihX"
    assert addr.email == "x@polytechnique.edu"


def test_message_flags():
    msg = Message(
        uid=1,
        flags=["\\Seen", "\\Flagged"],
        folder="INBOX",
    )
    assert msg.is_seen is True
    assert msg.is_flagged is True
    assert msg.has_attachments is False


def test_message_no_flags():
    msg = Message(uid=2, folder="INBOX")
    assert msg.is_seen is False
    assert msg.is_flagged is False


def test_folder_selectable():
    f = Folder(name="INBOX", attributes=[])
    assert f.is_selectable is True

    f2 = Folder(name="[Gmail]", attributes=["\\Noselect"])
    assert f2.is_selectable is False


def test_message_summary_defaults():
    s = MessageSummary(uid=10, folder="INBOX")
    assert s.subject == ""
    assert s.sender is None
    assert s.flags == []
