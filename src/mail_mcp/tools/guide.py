"""mail_guide — entry point for agents unfamiliar with this MCP."""

from fastmcp import FastMCP

from mail_mcp.config import get_config

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
# mail-mcp — Agent Guide

## Accounts
{account_list}

All tools accept an optional `account_id` parameter. Omit it to use the default account.

## Reading Tools
- `check_inbox` — fast unread count + last N summaries (start here)
- `daily_digest` — structured overview of today's inbox and flagged items
- `list_messages` — list messages in a folder with filters
- `get_message` — full message body + attachments list by UID
- `search_messages` — flexible search (query, sender, date range, flags)
- `get_thread` — all messages in a thread given a Message-ID
- `find_unread` — shortcut for unread messages

## Composing Tools
- `send_message` — send a new email
- `reply_message` — reply to a message by UID
- `forward_message` — forward a message by UID to new recipients
- `save_draft` — save a draft to the Drafts folder (IMAP APPEND)

## Management Tools
- `list_folders` — all IMAP folders
- `mark_messages` — add/remove flags (seen, flagged, answered)
- `move_messages` — move UIDs to a different folder
- `archive_messages` — move to Archive folder
- `delete_messages` — permanently delete UIDs
- `mark_as_spam` — move to Spam/Junk folder

## Typical Workflows

### Morning triage
1. `check_inbox` → see unread count
2. `daily_digest` → structured summary
3. `get_message(uid=...)` → read a specific message
4. `reply_message(uid=...)` → reply

### Find an email
1. `search_messages(query="budget report", since="2024-01-01")`

### Send a quick reply
1. `get_message(uid=123)` → read original
2. `reply_message(uid=123, body_text="...")`
"""
