"""Compose tools — send, reply, forward, save draft."""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from mail_mcp.config import get_account, get_default_account
from mail_mcp.core.imap_client import IMAPClient
from mail_mcp.core.smtp_client import SMTPClient

mcp = FastMCP("mail-compose")


def _account(account_id: Optional[str]):
    return get_account(account_id) if account_id else get_default_account()


@mcp.tool()
def send_message(
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    cc: Optional[list[str]] = None,
    signature: str = "default",
    attachments: Optional[list[str]] = None,
    account_id: Optional[str] = None,
) -> dict:
    """Send a new email message.

    - `to`: list of recipient email addresses
    - `subject`: email subject line
    - `body_text`: plain-text body (required)
    - `body_html`: optional HTML version
    - `cc`: optional CC recipients
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    - `attachments`: optional list of absolute file paths to attach

    Returns `{"sent": true, "message_id": "..."}` on success.
    """
    acc = _account(account_id)
    smtp = SMTPClient(acc)
    mid = smtp.send(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        cc=cc,
        signature=signature,
        attachments=attachments,
    )
    return {"sent": True, "message_id": mid, "account": acc.id}


@mcp.tool()
def reply_message(
    uid: int,
    body_text: str,
    body_html: str = "",
    reply_all: bool = False,
    signature: str = "default",
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Reply to a message by UID.

    Automatically sets In-Reply-To and References headers.
    Set `reply_all=True` to include all original recipients in CC.
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    Returns `{"sent": true, "message_id": "..."}` on success.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as imap:
        original = imap.fetch_message(uid, folder)

    if original is None:
        return {"error": f"Message UID {uid} not found in {folder}"}

    smtp = SMTPClient(acc)
    mid = smtp.reply(
        original=original,
        body_text=body_text,
        body_html=body_html,
        reply_all=reply_all,
        signature=signature,
    )
    return {"sent": True, "message_id": mid, "account": acc.id}


@mcp.tool()
def forward_message(
    uid: int,
    to: list[str],
    body_text: str = "",
    signature: str = "default",
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Forward a message by UID to new recipients.

    Prepends a standard forward header and the original body.
    `body_text` is prepended above the forwarded content.
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    Returns `{"sent": true, "message_id": "..."}` on success.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as imap:
        original = imap.fetch_message(uid, folder)

    if original is None:
        return {"error": f"Message UID {uid} not found in {folder}"}

    smtp = SMTPClient(acc)
    mid = smtp.forward(original=original, to=to, body_text=body_text, signature=signature)
    return {"sent": True, "message_id": mid, "account": acc.id}


@mcp.tool()
def save_draft(
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    cc: Optional[list[str]] = None,
    signature: str = "default",
    attachments: Optional[list[str]] = None,
    drafts_folder: str = "Drafts",
    account_id: Optional[str] = None,
) -> dict:
    """Save a message as a draft in the IMAP Drafts folder.

    The message is built locally and appended via IMAP APPEND — not sent.
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    - `attachments`: optional list of absolute file paths to attach
    Returns `{"saved": true, "message_id": "..."}` on success.
    """
    acc = _account(account_id)
    smtp = SMTPClient(acc)
    raw_bytes, mid = smtp.build_draft_bytes(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        cc=cc,
        signature=signature,
        attachments=attachments,
    )
    with IMAPClient(acc) as imap:
        imap.append_message(drafts_folder, raw_bytes, flags=["\\Draft"])

    return {"saved": True, "message_id": mid, "folder": drafts_folder, "account": acc.id}
