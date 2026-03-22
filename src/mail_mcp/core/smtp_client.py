"""SMTP client wrapper — handles sending, replying, forwarding, draft saving.

Uses only stdlib smtplib + email — no external SMTP library needed.
"""

from __future__ import annotations

import smtplib
import ssl
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from mail_mcp.config import AccountConfig
from mail_mcp.core.models import Address, Message


class SMTPClient:
    """Stateless SMTP sender — connects, sends, disconnects per call."""

    def __init__(self, account: AccountConfig) -> None:
        self.account = account

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> smtplib.SMTP:
        cfg = self.account.smtp
        if cfg.starttls:
            server = smtplib.SMTP(cfg.host, cfg.port, timeout=30)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        else:
            # Direct TLS (port 465)
            server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30)
        server.login(self.account.username, self.account.password)
        return server

    def _build_message(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str = "",
        cc: list[str] | None = None,
        in_reply_to: str = "",
        references: list[str] | None = None,
        message_id: str = "",
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative") if not body_html else MIMEMultipart("alternative")
        msg["From"] = formataddr(("", self.account.username))
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = message_id or make_msgid()

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = " ".join(references)

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        return msg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str = "",
        cc: list[str] | None = None,
    ) -> str:
        """Send a new message. Returns the generated Message-ID."""
        msg = self._build_message(to, subject, body_text, body_html, cc)
        mid = msg["Message-ID"]
        all_recipients = to + (cc or [])
        with self._connect() as server:
            server.sendmail(self.account.username, all_recipients, msg.as_bytes())
        return mid

    def reply(
        self,
        original: Message,
        body_text: str,
        body_html: str = "",
        reply_all: bool = False,
    ) -> str:
        """Reply to an existing message."""
        subject = original.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        to_list = [original.sender.email] if original.sender else []
        cc_list: list[str] = []
        if reply_all:
            existing_to = {a.email for a in original.recipients}
            existing_cc = {a.email for a in original.cc}
            me = self.account.username
            to_list = [e for e in existing_to if e != me] or to_list
            cc_list = [e for e in existing_cc if e != me]

        refs = original.references + ([original.message_id] if original.message_id else [])

        msg = self._build_message(
            to=to_list,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc_list or None,
            in_reply_to=original.message_id,
            references=refs,
        )
        mid = msg["Message-ID"]
        with self._connect() as server:
            server.sendmail(self.account.username, to_list + cc_list, msg.as_bytes())
        return mid

    def forward(
        self,
        original: Message,
        to: list[str],
        body_text: str = "",
    ) -> str:
        """Forward a message, prepending a standard forward header."""
        subject = original.subject
        if not subject.lower().startswith("fwd:") and not subject.lower().startswith("fw:"):
            subject = f"Fwd: {subject}"

        sender_str = original.sender.email if original.sender else "unknown"
        date_str = original.date.strftime("%Y-%m-%d %H:%M") if original.date else ""
        prefix = (
            f"\n\n---------- Forwarded message ----------\n"
            f"From: {sender_str}\n"
            f"Date: {date_str}\n"
            f"Subject: {original.subject}\n\n"
        )
        full_body = (body_text + prefix + original.body_text).strip()

        msg = self._build_message(to=to, subject=subject, body_text=full_body)
        mid = msg["Message-ID"]
        with self._connect() as server:
            server.sendmail(self.account.username, to, msg.as_bytes())
        return mid

    def build_draft_bytes(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str = "",
        cc: list[str] | None = None,
    ) -> tuple[bytes, str]:
        """Build a draft as raw bytes (to be APPEND-ed via IMAP). Returns (bytes, message_id)."""
        msg = self._build_message(to, subject, body_text, body_html, cc)
        return msg.as_bytes(), msg["Message-ID"]
