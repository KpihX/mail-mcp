"""IMAP client wrapper built on imapclient.

Design goals:
- Context-manager lifecycle (connect on enter, logout on exit)
- Returns domain models (Message, MessageSummary, Folder) — no raw IMAP tuples
- Generic: works with any IMAP4rev1 server (Zimbra, Gmail, Outlook, Dovecot…)
"""

from __future__ import annotations

import email
import email.header
import re
from contextlib import contextmanager
from datetime import datetime
from email.message import Message as EmailMessage
from typing import Generator, Optional

import html2text
import imapclient

from mail_mcp.config import AccountConfig
from mail_mcp.core.models import (
    Address,
    Attachment,
    Flag,
    Folder,
    Message,
    MessageSummary,
    SearchCriteria,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_header(raw: str | bytes | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode(errors="replace")
    parts = email.header.decode_header(raw)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return " ".join(decoded)


def _parse_address_list(raw: str | None) -> list[Address]:
    if not raw:
        return []
    # Rough RFC 2822 address parser — handles "Name <email>" and bare emails
    results = []
    for part in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", raw):
        part = part.strip()
        m = re.match(r'"?([^"<]*)"?\s*<([^>]+)>', part)
        if m:
            results.append(Address(name=m.group(1).strip(), email=m.group(2).strip()))
        elif "@" in part:
            results.append(Address(name="", email=part))
    return results


def _extract_text(msg: EmailMessage) -> tuple[str, str]:
    """Return (plain_text, html_text) from a parsed email."""
    plain, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if "attachment" in cd:
                continue
            if ct == "text/plain" and not plain:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                plain = payload.decode(charset, errors="replace") if payload else ""
            elif ct == "text/html" and not html:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace") if payload else ""
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace") if payload else ""
        ct = msg.get_content_type()
        if ct == "text/html":
            html = body
        else:
            plain = body

    # Convert html → plain if we only have html
    if html and not plain:
        h = html2text.HTML2Text()
        h.ignore_links = False
        plain = h.handle(html)

    return plain, html


def _extract_attachments(msg: EmailMessage, max_preview: int = 4096) -> list[Attachment]:
    attachments = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        cd = part.get("Content-Disposition", "")
        if "attachment" not in cd and "inline" not in cd:
            continue
        filename = _decode_header(part.get_filename())
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            Attachment(
                filename=filename,
                content_type=part.get_content_type(),
                size_bytes=len(payload),
            )
        )
    return attachments


# ---------------------------------------------------------------------------
# IMAP client
# ---------------------------------------------------------------------------


class IMAPClient:
    """Thin wrapper around imapclient.IMAPClient with domain-model returns."""

    def __init__(self, account: AccountConfig) -> None:
        self.account = account
        self._client: imapclient.IMAPClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> "IMAPClient":
        cfg = self.account.imap
        self._client = imapclient.IMAPClient(
            host=cfg.host,
            port=cfg.port,
            ssl=cfg.tls,
        )
        self._client.login(self.account.username, self.account.password)
        return self

    def disconnect(self) -> None:
        if self._client:
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None

    def __enter__(self) -> "IMAPClient":
        return self.connect()

    def __exit__(self, *_: object) -> None:
        self.disconnect()

    def _c(self) -> imapclient.IMAPClient:
        if self._client is None:
            raise RuntimeError("IMAP client is not connected — use as context manager")
        return self._client

    # ------------------------------------------------------------------
    # Folder operations
    # ------------------------------------------------------------------

    def list_folders(self) -> list[Folder]:
        folders = []
        for flags, delimiter, name in self._c().list_folders():
            folders.append(
                Folder(
                    name=name,
                    delimiter=delimiter.decode() if isinstance(delimiter, bytes) else delimiter,
                    attributes=[
                        f.decode() if isinstance(f, bytes) else f for f in flags
                    ],
                )
            )
        return folders

    def get_folder_status(self, folder: str = "INBOX") -> Folder:
        status = self._c().folder_status(folder, ["MESSAGES", "UNSEEN"])
        return Folder(
            name=folder,
            message_count=status.get(b"MESSAGES"),
            unseen_count=status.get(b"UNSEEN"),
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, criteria: SearchCriteria) -> list[int]:
        """Return a list of UIDs matching the search criteria."""
        self._c().select_folder(criteria.folder, readonly=True)

        imap_criteria: list[object] = []

        if criteria.unseen_only:
            imap_criteria.append("UNSEEN")
        if criteria.flagged_only:
            imap_criteria.append("FLAGGED")
        if criteria.sender:
            imap_criteria += ["FROM", criteria.sender]
        if criteria.since:
            imap_criteria += ["SINCE", criteria.since.date()]
        if criteria.before:
            imap_criteria += ["BEFORE", criteria.before.date()]
        if criteria.query:
            imap_criteria += ["OR", ["SUBJECT", criteria.query], ["BODY", criteria.query]]
        if criteria.has_attachment:
            imap_criteria += ["HEADER", "Content-Type", "multipart"]

        if not imap_criteria:
            imap_criteria = ["ALL"]

        uids = self._c().search(imap_criteria, "UTF-8")
        # Return newest first, limited
        uids = sorted(uids, reverse=True)
        return uids[: criteria.limit]

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def fetch_summaries(self, uids: list[int], folder: str = "INBOX") -> list[MessageSummary]:
        if not uids:
            return []
        self._c().select_folder(folder, readonly=True)
        data = self._c().fetch(uids, ["ENVELOPE", "FLAGS", "BODYSTRUCTURE"])
        summaries = []
        for uid, msg_data in data.items():
            envelope = msg_data.get(b"ENVELOPE")
            flags = [
                f.decode() if isinstance(f, bytes) else f
                for f in msg_data.get(b"FLAGS", [])
            ]
            if envelope is None:
                continue
            subject = _decode_header(envelope.subject)
            sender = None
            if envelope.from_:
                addr = envelope.from_[0]
                name = _decode_header(addr.name) if addr.name else ""
                mailbox = addr.mailbox.decode() if addr.mailbox else ""
                host = addr.host.decode() if addr.host else ""
                sender = Address(name=name, email=f"{mailbox}@{host}")
            date = None
            if envelope.date:
                date = envelope.date

            summaries.append(
                MessageSummary(
                    uid=uid,
                    subject=subject,
                    sender=sender,
                    date=date,
                    flags=flags,
                    folder=folder,
                    account_id=self.account.id,
                )
            )
        return sorted(summaries, key=lambda m: m.date or datetime.min, reverse=True)

    def fetch_message(self, uid: int, folder: str = "INBOX") -> Optional[Message]:
        self._c().select_folder(folder, readonly=True)
        data = self._c().fetch([uid], ["RFC822", "FLAGS"])
        if uid not in data:
            return None

        raw = data[uid].get(b"RFC822", b"")
        flags = [
            f.decode() if isinstance(f, bytes) else f
            for f in data[uid].get(b"FLAGS", [])
        ]

        msg = email.message_from_bytes(raw)
        plain, html = _extract_text(msg)
        attachments = _extract_attachments(msg)

        sender = None
        from_raw = msg.get("From", "")
        addrs = _parse_address_list(from_raw)
        if addrs:
            sender = addrs[0]

        recipients = _parse_address_list(msg.get("To", ""))
        cc = _parse_address_list(msg.get("Cc", ""))

        date_str = msg.get("Date", "")
        date: Optional[datetime] = None
        if date_str:
            from email.utils import parsedate_to_datetime
            try:
                date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        refs_raw = msg.get("References", "")
        references = [r.strip() for r in refs_raw.split() if r.strip()]

        return Message(
            uid=uid,
            message_id=msg.get("Message-ID", ""),
            subject=_decode_header(msg.get("Subject", "")),
            sender=sender,
            recipients=recipients,
            cc=cc,
            date=date,
            flags=flags,
            folder=folder,
            body_text=plain,
            body_html=html,
            attachments=attachments,
            in_reply_to=msg.get("In-Reply-To", ""),
            references=references,
            account_id=self.account.id,
        )

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def set_flags(self, uids: list[int], folder: str, flags: list[str], add: bool = True) -> None:
        self._c().select_folder(folder)
        if add:
            self._c().add_flags(uids, flags)
        else:
            self._c().remove_flags(uids, flags)

    def move_messages(self, uids: list[int], src_folder: str, dst_folder: str) -> None:
        self._c().select_folder(src_folder)
        # Use MOVE if supported, else copy+delete
        capabilities = self._c().capabilities()
        if b"MOVE" in capabilities:
            self._c().move(uids, dst_folder)
        else:
            self._c().copy(uids, dst_folder)
            self._c().delete_messages(uids)
            self._c().expunge()

    def delete_messages(self, uids: list[int], folder: str) -> None:
        self._c().select_folder(folder)
        self._c().delete_messages(uids)
        self._c().expunge()

    def expunge(self) -> None:
        self._c().expunge()

    def append_message(self, folder: str, raw_message: bytes, flags: list[str] | None = None) -> int | None:
        """Append a raw RFC822 message to a folder (e.g. Drafts/Sent)."""
        result = self._c().append(folder, raw_message, flags or [], None)
        # Some servers return the UID of the appended message
        return result if isinstance(result, int) else None
