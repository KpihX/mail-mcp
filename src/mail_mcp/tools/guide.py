"""mail_guide — entry point for agents unfamiliar with this MCP."""

from fastmcp import FastMCP

from mail_mcp.config import APP_VERSION, get_config

mcp = FastMCP("mail-guide")


@mcp.tool()
def mail_guide() -> str:
    """Return a complete guide of available tools and best usage patterns for mail-mcp.

    Call this first when starting a mail-related session to orient yourself.
    """
    config = get_config()
    account_list = "\n".join(
        f"  - {a.id} ({a.label}){' [default]' if a.default else ''}"
        for a in config.accounts
    )

    return f"""
# mail-mcp v{APP_VERSION} — Agent Guide

## Transports (same tools, different host)
- **stdio** (`mail-mcp serve`) — use on the machine where **local attachment paths** exist.
- **HTTP** (`mail-mcp serve-http`, path `/mcp`) — homelab / remote; **cannot** read arbitrary files on your laptop.

## Accounts
{account_list}

All tools accept an optional `account_id` parameter. Omit it to use the default account.

## Reading Tools
- `check_inbox` — fast unread count + last N summaries (start here)
- `daily_digest` — structured overview of today's inbox and flagged items
- `list_messages` — list messages in a folder with filters (unseen_only, flagged_only)
- `get_message` — full message body + attachments metadata by UID
- `download_attachment` — save an attachment to a local file by filename
- `search_messages` — powerful search: IMAP filters + client-side regex (see below)
- `get_thread` — full thread by Message-ID (oldest-first)
- `find_unread` — shortcut: unread messages in a folder

## search_messages filters
IMAP level (server-side, fast):
  `sender`, `subject_filter`, `to_filter`, `cc_filter` — substring match
  `query` — OR search in subject + body
  `keyword` — custom IMAP keyword/label
  `since` / `before` — ISO date strings
  `unseen_only`, `flagged_only`, `has_attachment`
  `min_size` / `max_size` — size in bytes
  `folder` (single) or `folders` (list, multi-folder)

Client-side regex (applied after IMAP, on fetched results):
  `sender_pattern` — regex on From address (e.g. ".*@polytechnique\\.edu")
  `subject_pattern` — regex on Subject
  `body_pattern` — regex on body text (expensive: fetches full messages)

## Composing Tools
- `send_message` — send new email (cc, bcc, attachments, signature, optional bounce probe)
- `reply_message` — reply by UID (bcc, signature, reply_all, optional bounce probe)
- `forward_message` — forward by UID (cc, bcc, signature, optional bounce probe)
- `save_draft` — save draft to Drafts folder (bcc, attachments, signature)

**SMTP vs delivery (all compose sends):**
- `smtp_accepted` — outbound SMTP accepted the message (mirrored by legacy `sent`).
- `saved_to_sent` / `sent_folder` — IMAP append of a copy to Sent when configured.
- `delivery_status` — `unknown` (default) | `bounced` | `delivered_hint` (see below).
- `bounce_details` — when a match is found: DSN / `MAILER-DAEMON` message in INBOX referencing the outbound `Message-ID`.

**Optional probe:** set `verify_bounce_window_seconds` > 0 to wait that many seconds after send, then scan INBOX for an immediate DSN/bounce. Default `0` skips the wait (status often stays `unknown`). Use a short window only when you need automated bounce detection; pair with human checks for sensitive mail per your agent policy.

Signature param: "default" → configured sig with logo | "" → none | "any text" → custom plain
BCC: added to SMTP envelope only — never appears in message headers.
Attachments: list of absolute local file paths (stdio transport on the host that owns those paths).

## Management Tools
- `list_folders` — all IMAP folders
- `create_folder` / `delete_folder` / `rename_folder` — folder CRUD
- `mark_messages` — add/remove standard flags (seen, flagged, answered, draft)
- `list_labels` — user-defined IMAP keyword labels on a folder (PERMANENTFLAGS)
- `set_labels` — add/remove custom keyword labels on messages
- `move_messages` — move UIDs between folders
- `archive_messages` — move to Archive (auto-detected folder name)
- `trash_messages` — move to Trash (recoverable delete)
- `delete_messages` — permanently delete + expunge (irreversible)
- `mark_as_spam` — move to Spam/Junk

## Typical Workflows

### Morning triage
1. `check_inbox` — unread count
2. `daily_digest` — structured overview
3. `get_message(uid=...)` — read a message
4. `reply_message(uid=..., body_text="...")` — reply

### Find emails from a domain
`search_messages(sender_pattern=".*@company\\.com", folders=["INBOX", "Archive"])`

### Download an attachment
1. `get_message(uid=123)` → note filename from attachments list
2. `download_attachment(uid=123, filename="report.pdf")` → saves to /tmp/mail_attachments/

### Send with BCC and attachment
`send_message(to=["x@y.com"], bcc=["z@w.com"], subject="...", body_text="...", attachments=["/path/to/file.pdf"])`

### Label management
1. `list_labels(folder="INBOX")` — see available labels
2. `set_labels(uids=[123, 124], labels=["todo"], add=True)` — tag messages
"""
