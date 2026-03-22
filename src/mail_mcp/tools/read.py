"""Read tools — inbox access, message fetch, search, threads."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from mail_mcp.config import get_account, get_config, get_default_account
from mail_mcp.core.imap_client import IMAPClient
from mail_mcp.core.models import SearchCriteria

mcp = FastMCP("mail-read")


def _account(account_id: Optional[str]):
    return get_account(account_id) if account_id else get_default_account()


@mcp.tool()
def check_inbox(
    limit: int = 10,
    account_id: Optional[str] = None,
) -> dict:
    """Quick inbox check: unread count + last N message summaries.

    Use this as the entry point for any mail-related session.
    Returns a compact dict with `unread_count` and `messages` list.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        status = client.get_folder_status("INBOX")
        criteria = SearchCriteria(folder="INBOX", unseen_only=True, limit=limit)
        uids = client.search(criteria)
        summaries = client.fetch_summaries(uids, "INBOX")

    return {
        "account": acc.id,
        "unread_count": status.unseen_count or 0,
        "total_count": status.message_count or 0,
        "messages": [
            {
                "uid": m.uid,
                "subject": m.subject,
                "from": m.sender.email if m.sender else "",
                "date": m.date.isoformat() if m.date else "",
                "flags": m.flags,
            }
            for m in summaries
        ],
    }


@mcp.tool()
def daily_digest(account_id: Optional[str] = None) -> dict:
    """Structured daily overview: unread, flagged, and today's messages.

    Ideal as the first tool called at the start of a session.
    """
    acc = _account(account_id)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    with IMAPClient(acc) as client:
        inbox_status = client.get_folder_status("INBOX")

        # Unread
        unread_uids = client.search(
            SearchCriteria(folder="INBOX", unseen_only=True, limit=20)
        )
        unread = client.fetch_summaries(unread_uids, "INBOX")

        # Flagged
        flagged_uids = client.search(
            SearchCriteria(folder="INBOX", flagged_only=True, limit=10)
        )
        flagged = client.fetch_summaries(flagged_uids, "INBOX")

        # Today
        today_uids = client.search(
            SearchCriteria(folder="INBOX", since=today_start, limit=20)
        )
        today_msgs = client.fetch_summaries(today_uids, "INBOX")

    def _fmt(summaries):
        return [
            {
                "uid": m.uid,
                "subject": m.subject,
                "from": m.sender.email if m.sender else "",
                "date": m.date.isoformat() if m.date else "",
            }
            for m in summaries
        ]

    return {
        "account": acc.id,
        "date": today_start.date().isoformat(),
        "inbox": {
            "total": inbox_status.message_count or 0,
            "unread": inbox_status.unseen_count or 0,
        },
        "unread_messages": _fmt(unread),
        "flagged_messages": _fmt(flagged),
        "received_today": _fmt(today_msgs),
    }


@mcp.tool()
def list_messages(
    folder: str = "INBOX",
    limit: int = 20,
    unseen_only: bool = False,
    flagged_only: bool = False,
    account_id: Optional[str] = None,
) -> list[dict]:
    """List messages in a folder.

    Returns lightweight summaries (uid, subject, from, date, flags).
    Use `get_message` to fetch the full body of a specific UID.
    """
    acc = _account(account_id)
    criteria = SearchCriteria(
        folder=folder,
        unseen_only=unseen_only,
        flagged_only=flagged_only,
        limit=limit,
    )
    with IMAPClient(acc) as client:
        uids = client.search(criteria)
        summaries = client.fetch_summaries(uids, folder)

    return [
        {
            "uid": m.uid,
            "subject": m.subject,
            "from": m.sender.email if m.sender else "",
            "date": m.date.isoformat() if m.date else "",
            "flags": m.flags,
            "has_attachments": m.has_attachments,
            "folder": m.folder,
        }
        for m in summaries
    ]


@mcp.tool()
def get_message(
    uid: int,
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Fetch the full content of a message by UID.

    Returns subject, from, to, cc, date, body_text, attachments list, and thread headers.
    UID and folder are required — use `list_messages` or `search_messages` to find UIDs.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        msg = client.fetch_message(uid, folder)

    if msg is None:
        return {"error": f"Message UID {uid} not found in {folder}"}

    return {
        "uid": msg.uid,
        "message_id": msg.message_id,
        "subject": msg.subject,
        "from": {"name": msg.sender.name, "email": msg.sender.email} if msg.sender else None,
        "to": [{"name": a.name, "email": a.email} for a in msg.recipients],
        "cc": [{"name": a.name, "email": a.email} for a in msg.cc],
        "date": msg.date.isoformat() if msg.date else "",
        "flags": msg.flags,
        "folder": msg.folder,
        "body_text": msg.body_text,
        "attachments": [
            {"filename": a.filename, "content_type": a.content_type, "size_bytes": a.size_bytes}
            for a in msg.attachments
        ],
        "in_reply_to": msg.in_reply_to,
        "references": msg.references,
    }


@mcp.tool()
def search_messages(
    query: Optional[str] = None,
    sender: Optional[str] = None,
    sender_pattern: Optional[str] = None,
    subject_filter: Optional[str] = None,
    subject_pattern: Optional[str] = None,
    to_filter: Optional[str] = None,
    cc_filter: Optional[str] = None,
    body_pattern: Optional[str] = None,
    keyword: Optional[str] = None,
    folder: str = "INBOX",
    folders: Optional[list[str]] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    unseen_only: bool = False,
    flagged_only: bool = False,
    has_attachment: bool = False,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    limit: int = 20,
    account_id: Optional[str] = None,
) -> list[dict]:
    """Search messages with flexible IMAP + client-side filters.

    **IMAP-level (fast, server-side):**
    - `query`: text match in subject OR body
    - `sender`: FROM substring (e.g. "@gmail.com")
    - `subject_filter`: SUBJECT substring
    - `to_filter`: TO field substring
    - `cc_filter`: CC field substring
    - `keyword`: custom IMAP keyword/label (e.g. "important", "\\\\Flagged")
    - `since` / `before`: ISO date "2024-03-01"
    - `unseen_only`, `flagged_only`, `has_attachment`
    - `min_size` / `max_size`: size in bytes
    - `folder`: default INBOX | `folders`: list for multi-folder search

    **Client-side regex (applied after IMAP, on fetched summaries):**
    - `sender_pattern`: regex on full From address (e.g. ".*@polytechnique\\\\.edu")
    - `subject_pattern`: regex on Subject line
    - `body_pattern`: regex on body text — **expensive**, fetches full messages

    Returns summaries — use `get_message` for full body.
    """
    acc = _account(account_id)

    since_dt = datetime.fromisoformat(since) if since else None
    before_dt = datetime.fromisoformat(before) if before else None

    # Expand limit to allow client-side regex to trim down after filtering
    fetch_limit = limit * 5 if (sender_pattern or subject_pattern or body_pattern) else limit

    criteria = SearchCriteria(
        folder=folder,
        folders=folders,
        query=query,
        sender=sender,
        subject_filter=subject_filter,
        to_filter=to_filter,
        cc_filter=cc_filter,
        since=since_dt,
        before=before_dt,
        unseen_only=unseen_only,
        flagged_only=flagged_only,
        has_attachment=has_attachment,
        min_size=min_size,
        max_size=max_size,
        keyword=keyword,
        limit=fetch_limit,
        account_id=acc.id,
    )

    with IMAPClient(acc) as client:
        uids = client.search(criteria)
        target_folder = (folders or [folder])[0]
        summaries = client.fetch_summaries(uids, target_folder)

        # Client-side regex on sender / subject (no extra fetch needed)
        if sender_pattern:
            rx = re.compile(sender_pattern, re.IGNORECASE)
            summaries = [m for m in summaries if m.sender and rx.search(m.sender.email + " " + m.sender.name)]
        if subject_pattern:
            rx = re.compile(subject_pattern, re.IGNORECASE)
            summaries = [m for m in summaries if rx.search(m.subject)]

        # Client-side regex on body — requires full fetch (expensive)
        if body_pattern:
            rx = re.compile(body_pattern, re.IGNORECASE | re.DOTALL)
            remaining_uids = [m.uid for m in summaries]
            full_msgs = client.fetch_messages_for_pattern(remaining_uids, target_folder)
            matching_uids = {uid for uid, _f, _s, body in full_msgs if rx.search(body)}
            summaries = [m for m in summaries if m.uid in matching_uids]

    # Apply final limit after regex filtering
    summaries = summaries[:limit]

    return [
        {
            "uid": m.uid,
            "subject": m.subject,
            "from": m.sender.email if m.sender else "",
            "date": m.date.isoformat() if m.date else "",
            "flags": m.flags,
            "has_attachments": m.has_attachments,
            "folder": m.folder,
        }
        for m in summaries
    ]


@mcp.tool()
def download_attachment(
    uid: int,
    filename: str,
    save_path: Optional[str] = None,
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Download an attachment from a message to a local file.

    - `uid`: message UID (from `get_message` → attachments list)
    - `filename`: exact filename as returned by `get_message`
    - `save_path`: absolute path to save to (default: /tmp/mail_attachments/<filename>)
    - `folder`: folder where the message lives

    Returns `{"saved_to": "...", "filename": "...", "size_bytes": N}`.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        data = client.download_attachment(uid, filename, folder)

    dest = Path(save_path) if save_path else Path("/tmp/mail_attachments") / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    return {
        "saved_to": str(dest),
        "filename": filename,
        "size_bytes": len(data),
        "account": acc.id,
    }


@mcp.tool()
def find_unread(
    folder: str = "INBOX",
    limit: int = 20,
    account_id: Optional[str] = None,
) -> list[dict]:
    """Shortcut: list unread messages in a folder. Equivalent to list_messages(unseen_only=True)."""
    return list_messages(
        folder=folder,
        limit=limit,
        unseen_only=True,
        account_id=account_id,
    )


@mcp.tool()
def get_thread(
    message_id: str,
    folder: str = "INBOX",
    limit: int = 50,
    account_id: Optional[str] = None,
) -> list[dict]:
    """Retrieve all messages in a thread by Message-ID.

    Returns messages ordered oldest-first (conversation view).
    Searches for messages that reference the given Message-ID.
    """
    acc = _account(account_id)
    config = get_config()
    depth_limit = min(limit, config.mcp.thread_depth_limit)

    with IMAPClient(acc) as client:
        # Search for the original + all replies (header-based)
        uids = client.search(
            SearchCriteria(folder=folder, query=message_id, limit=depth_limit)
        )
        summaries = client.fetch_summaries(uids, folder)

    return [
        {
            "uid": m.uid,
            "subject": m.subject,
            "from": m.sender.email if m.sender else "",
            "date": m.date.isoformat() if m.date else "",
            "flags": m.flags,
        }
        for m in sorted(summaries, key=lambda m: m.date or datetime.min)
    ]
