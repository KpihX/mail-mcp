"""Compose tools — send, reply, forward, save draft."""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from mail_mcp.config import get_account, get_default_account
from mail_mcp.core.imap_client import IMAPClient
from mail_mcp.core.smtp_client import SMTPClient

mcp = FastMCP("mail-compose")

_SENT_CANDIDATES = ["Sent", "Sent Items", "Sent Messages", "[Gmail]/Sent Mail"]


def _account(account_id: Optional[str]):
    return get_account(account_id) if account_id else get_default_account()

def _resolve_sent_folder(imap: IMAPClient) -> str:
    existing = {f.name for f in imap.list_folders()}
    for name in _SENT_CANDIDATES:
        if name in existing:
            return name
    return _SENT_CANDIDATES[0]

def _save_copy_to_sent(
    *,
    acc,
    smtp: SMTPClient,
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    signature: str = "default",
    attachments: Optional[list[str]] = None,
) -> tuple[bool, str]:
    raw_bytes, _ = smtp.build_draft_bytes(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        signature=signature,
        attachments=attachments,
    )
    with IMAPClient(acc) as imap:
        sent_folder = _resolve_sent_folder(imap)
        imap.append_message(sent_folder, raw_bytes, flags=[])
    return True, sent_folder


@mcp.tool()
def send_message(
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    signature: str = "default",
    attachments: Optional[list[str]] = None,
    account_id: Optional[str] = None,
) -> dict:
    """Send a new email message.

    - `to`: list of recipient email addresses
    - `subject`: email subject line
    - `body_text`: plain-text body (required)
    - `body_html`: optional HTML version
    - `cc`: carbon copy recipients (visible in headers)
    - `bcc`: blind carbon copy (added to SMTP envelope only — recipients never see it)
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    - `attachments`: optional list of absolute file paths to attach

    Returns `{"sent": true, "message_id": "...", "saved_to_sent": bool}`.
    """
    acc = _account(account_id)
    smtp = SMTPClient(acc)
    mid = smtp.send(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        signature=signature,
        attachments=attachments,
    )
    saved_to_sent = False
    sent_folder = ""
    try:
        saved_to_sent, sent_folder = _save_copy_to_sent(
            acc=acc,
            smtp=smtp,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            signature=signature,
            attachments=attachments,
        )
    except Exception:
        saved_to_sent = False
    return {
        "sent": True,
        "message_id": mid,
        "account": acc.id,
        "saved_to_sent": saved_to_sent,
        "sent_folder": sent_folder,
    }


@mcp.tool()
def reply_message(
    uid: int,
    body_text: str,
    body_html: str = "",
    reply_all: bool = False,
    bcc: Optional[list[str]] = None,
    signature: str = "default",
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Reply to a message by UID.

    Automatically sets In-Reply-To and References headers.
    Set `reply_all=True` to include all original recipients in CC.
    - `bcc`: blind carbon copy (envelope only)
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    Returns `{"sent": true, "message_id": "...", "saved_to_sent": bool}`.
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
        bcc=bcc,
        signature=signature,
    )
    saved_to_sent = False
    sent_folder = ""
    try:
        subject = original.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        to_copy = [original.sender.email] if original.sender else []
        cc_copy: list[str] = []
        if reply_all:
            me = acc.from_address
            to_copy = [e for e in {a.email for a in original.recipients} if e != me] or to_copy
            cc_copy = [e for e in {a.email for a in original.cc} if e != me]
        saved_to_sent, sent_folder = _save_copy_to_sent(
            acc=acc,
            smtp=smtp,
            to=to_copy,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc_copy or None,
            bcc=bcc,
            signature=signature,
        )
    except Exception:
        saved_to_sent = False
    return {
        "sent": True,
        "message_id": mid,
        "account": acc.id,
        "saved_to_sent": saved_to_sent,
        "sent_folder": sent_folder,
    }


@mcp.tool()
def forward_message(
    uid: int,
    to: list[str],
    body_text: str = "",
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    signature: str = "default",
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Forward a message by UID to new recipients.

    Prepends a standard forward header and the original body.
    `body_text` is prepended above the forwarded content.
    - `cc`: visible carbon copy
    - `bcc`: blind carbon copy (envelope only)
    - `signature`: "default" → configured signature with logo | "" → none | "any text" → custom plain-text sig
    Returns `{"sent": true, "message_id": "...", "saved_to_sent": bool}`.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as imap:
        original = imap.fetch_message(uid, folder)

    if original is None:
        return {"error": f"Message UID {uid} not found in {folder}"}

    smtp = SMTPClient(acc)
    mid = smtp.forward(original=original, to=to, body_text=body_text, cc=cc, bcc=bcc, signature=signature)
    saved_to_sent = False
    sent_folder = ""
    try:
        full_body = (
            body_text
            + f"\n\n---------- Forwarded message ----------\n"
            + f"From: {original.sender.email if original.sender else 'unknown'}\n"
            + f"Date: {original.date.strftime('%Y-%m-%d %H:%M') if original.date else ''}\n"
            + f"Subject: {original.subject}\n\n"
            + original.body_text
        ).strip()
        subject = original.subject
        if not subject.lower().startswith("fwd:") and not subject.lower().startswith("fw:"):
            subject = f"Fwd: {subject}"
        saved_to_sent, sent_folder = _save_copy_to_sent(
            acc=acc,
            smtp=smtp,
            to=to,
            subject=f"Fwd: {original.subject}",
            body_text=full_body,
            cc=cc,
            bcc=bcc,
            signature=signature,
        )
    except Exception:
        saved_to_sent = False
    return {
        "sent": True,
        "message_id": mid,
        "account": acc.id,
        "saved_to_sent": saved_to_sent,
        "sent_folder": sent_folder,
    }


@mcp.tool()
def save_draft(
    to: list[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
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
        bcc=bcc,
        signature=signature,
        attachments=attachments,
    )
    with IMAPClient(acc) as imap:
        imap.append_message(drafts_folder, raw_bytes, flags=["\\Draft"])

    return {"saved": True, "message_id": mid, "folder": drafts_folder, "account": acc.id}
