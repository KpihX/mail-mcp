"""Pydantic models for mail-mcp — transport-agnostic representations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Flag(str, Enum):
    SEEN = "\\Seen"
    ANSWERED = "\\Answered"
    FLAGGED = "\\Flagged"
    DELETED = "\\Deleted"
    DRAFT = "\\Draft"


class Address(BaseModel):
    name: str = ""
    email: str


class Attachment(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    # Content is omitted by default; fetched on demand
    content_b64: Optional[str] = None


class Message(BaseModel):
    uid: int
    message_id: str = ""
    subject: str = ""
    sender: Optional[Address] = None
    recipients: list[Address] = Field(default_factory=list)
    cc: list[Address] = Field(default_factory=list)
    date: Optional[datetime] = None
    flags: list[str] = Field(default_factory=list)
    folder: str = "INBOX"
    body_text: str = ""       # plain-text body (html2text conversion if needed)
    body_html: str = ""       # raw HTML if available
    attachments: list[Attachment] = Field(default_factory=list)
    in_reply_to: str = ""
    references: list[str] = Field(default_factory=list)
    account_id: str = ""

    @property
    def is_seen(self) -> bool:
        return Flag.SEEN in self.flags

    @property
    def is_flagged(self) -> bool:
        return Flag.FLAGGED in self.flags

    @property
    def has_attachments(self) -> bool:
        return len(self.attachments) > 0


class MessageSummary(BaseModel):
    """Lightweight listing row — avoids fetching full bodies."""
    uid: int
    message_id: str = ""
    subject: str = ""
    sender: Optional[Address] = None
    date: Optional[datetime] = None
    flags: list[str] = Field(default_factory=list)
    folder: str = "INBOX"
    has_attachments: bool = False
    account_id: str = ""


class Folder(BaseModel):
    name: str
    delimiter: str = "/"
    attributes: list[str] = Field(default_factory=list)
    message_count: Optional[int] = None
    unseen_count: Optional[int] = None

    @property
    def is_selectable(self) -> bool:
        return "\\Noselect" not in self.attributes


class SearchCriteria(BaseModel):
    folder: str = "INBOX"
    folders: Optional[list[str]] = None        # multi-folder search (overrides folder)
    query: Optional[str] = None                # IMAP OR SUBJECT+BODY text search
    sender: Optional[str] = None               # IMAP FROM substring
    subject_filter: Optional[str] = None       # IMAP SUBJECT substring
    to_filter: Optional[str] = None            # IMAP TO substring
    cc_filter: Optional[str] = None            # IMAP CC substring
    since: Optional[datetime] = None
    before: Optional[datetime] = None
    unseen_only: bool = False
    flagged_only: bool = False
    has_attachment: bool = False
    min_size: Optional[int] = None             # IMAP LARGER (bytes)
    max_size: Optional[int] = None             # IMAP SMALLER (bytes)
    keyword: Optional[str] = None              # IMAP KEYWORD (custom flag/label)
    sender_pattern: Optional[str] = None       # client-side regex on From address
    subject_pattern: Optional[str] = None      # client-side regex on Subject
    body_pattern: Optional[str] = None         # client-side regex on body (expensive)
    limit: int = 20
    account_id: Optional[str] = None
