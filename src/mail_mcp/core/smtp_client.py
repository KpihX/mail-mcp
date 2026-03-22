"""SMTP client wrapper — handles sending, replying, forwarding, draft saving.

Signature handling:
- Plain text: appended after body with a "--" separator
- HTML: multipart/related wrapping multipart/alternative, logo embedded as CID

MIME structure when signature logo is present:
  multipart/related
    ├── multipart/alternative
    │     ├── text/plain  (body + text signature)
    │     └── text/html   (body + HTML signature with <img src="cid:sig_logo">)
    └── image/png         (logo, Content-ID: sig_logo)
"""

from __future__ import annotations

import mimetypes
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from mail_mcp.config import AccountConfig, SignatureConfig
from mail_mcp.core.models import Message

_PKG_DIR = Path(__file__).parent.parent   # src/mail_mcp/
_SIG_CID = "sig_logo_polytechnique"


# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------


def _sig_text(sig: SignatureConfig) -> str:
    """Plain-text signature block."""
    if not sig.before_logo and not sig.after_logo:
        return ""
    parts = []
    if sig.before_logo:
        parts.append(sig.before_logo.strip())
    if sig.after_logo:
        parts.append(sig.after_logo.strip())
    return "\n\n--\n" + "\n".join(parts)


def _sig_html(sig: SignatureConfig) -> str:
    """HTML signature block (uses CID reference for logo)."""
    before = sig.before_logo.strip().replace("\n", "<br>") if sig.before_logo else ""
    after = sig.after_logo.strip().replace("\n", "<br>") if sig.after_logo else ""

    logo_html = ""
    if sig.logo_path:
        logo_html = (
            f'<img src="cid:{_SIG_CID}" alt="Ecole Polytechnique / Institut Polytechnique de Paris"'
            f' style="max-width:280px; display:block; margin:6px 0;">'
        )

    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#1a1a2e;line-height:1.5;">'
        f"<p style='margin:0 0 4px 0;'><strong>{before}</strong></p>"
        f"{logo_html}"
        f"<p style='margin:4px 0 0 0;'>{after}</p>"
        "</div>"
    )


def _load_logo(sig: SignatureConfig) -> bytes | None:
    """Load the logo image bytes from the configured path (relative to package dir)."""
    if not sig.logo_path:
        return None
    logo_path = _PKG_DIR / sig.logo_path
    if not logo_path.exists():
        return None
    return logo_path.read_bytes()


# ---------------------------------------------------------------------------
# SMTP client
# ---------------------------------------------------------------------------


class SMTPClient:
    """Stateless SMTP sender — connects, sends, disconnects per call."""

    def __init__(self, account: AccountConfig) -> None:
        self.account = account

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> smtplib.SMTP:
        cfg = self.account.smtp
        if cfg.starttls:
            server = smtplib.SMTP(cfg.host, cfg.port, timeout=30)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30)
        server.login(self.account.username, self.account.password)
        return server

    # ------------------------------------------------------------------
    # Message builder
    # ------------------------------------------------------------------

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
        include_signature: bool = True,
    ) -> MIMEMultipart:
        sig = self.account.signature
        logo_bytes = _load_logo(sig) if include_signature else None

        # Build text part (body + plain sig)
        full_text = body_text
        if include_signature:
            full_text += _sig_text(sig)

        # Build HTML part (body + html sig)
        if body_html or (include_signature and (sig.before_logo or sig.after_logo)):
            body_html_content = body_html or f"<p>{body_text.replace(chr(10), '<br>')}</p>"
            full_html = (
                body_html_content
                + ('<hr style="border:none;border-top:1px solid #ccc;margin:16px 0;">'
                   + _sig_html(sig) if include_signature else "")
            )
        else:
            full_html = ""

        # Determine top-level structure
        # With logo → multipart/related wrapping multipart/alternative
        # Without logo → multipart/alternative directly
        if logo_bytes and include_signature:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(full_text, "plain", "utf-8"))
            alt.attach(MIMEText(full_html, "html", "utf-8"))

            related = MIMEMultipart("related")
            related.attach(alt)

            img = MIMEImage(logo_bytes)
            img.add_header("Content-ID", f"<{_SIG_CID}>")
            img.add_header("Content-Disposition", "inline", filename="logo.png")
            related.attach(img)

            root = MIMEMultipart("mixed")
            root.attach(related)
        elif full_html:
            root = MIMEMultipart("alternative")
            root.attach(MIMEText(full_text, "plain", "utf-8"))
            root.attach(MIMEText(full_html, "html", "utf-8"))
        else:
            root = MIMEMultipart("alternative")
            root.attach(MIMEText(full_text, "plain", "utf-8"))

        # Headers on root
        root["From"] = formataddr((self.account.display_name, self.account.from_address))
        root["To"] = ", ".join(to)
        if cc:
            root["Cc"] = ", ".join(cc)
        root["Subject"] = subject
        root["Date"] = formatdate(localtime=True)
        root["Message-ID"] = message_id or make_msgid()
        if in_reply_to:
            root["In-Reply-To"] = in_reply_to
        if references:
            root["References"] = " ".join(references)

        return root

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
        """Send a new message with auto-injected signature. Returns Message-ID."""
        msg = self._build_message(to, subject, body_text, body_html, cc)
        mid = msg["Message-ID"]
        with self._connect() as server:
            server.sendmail(self.account.from_address, to + (cc or []), msg.as_bytes())
        return mid

    def reply(
        self,
        original: Message,
        body_text: str,
        body_html: str = "",
        reply_all: bool = False,
    ) -> str:
        """Reply to an existing message with auto-injected signature."""
        subject = original.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        to_list = [original.sender.email] if original.sender else []
        cc_list: list[str] = []
        if reply_all:
            me = self.account.from_address
            to_list = [e for e in {a.email for a in original.recipients} if e != me] or to_list
            cc_list = [e for e in {a.email for a in original.cc} if e != me]

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
            server.sendmail(self.account.from_address, to_list + cc_list, msg.as_bytes())
        return mid

    def forward(
        self,
        original: Message,
        to: list[str],
        body_text: str = "",
    ) -> str:
        """Forward a message with auto-injected signature."""
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
            server.sendmail(self.account.from_address, to, msg.as_bytes())
        return mid

    def build_draft_bytes(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: str = "",
        cc: list[str] | None = None,
    ) -> tuple[bytes, str]:
        """Build a draft as raw bytes for IMAP APPEND. Returns (bytes, message_id)."""
        msg = self._build_message(to, subject, body_text, body_html, cc)
        return msg.as_bytes(), msg["Message-ID"]
