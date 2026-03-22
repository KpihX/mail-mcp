"""Management tools — folders, flags, move, archive, delete, spam."""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from mail_mcp.config import get_account, get_default_account
from mail_mcp.core.imap_client import IMAPClient

mcp = FastMCP("mail-manage")

# Common folder name variants (Zimbra + standard)
_ARCHIVE_CANDIDATES = ["Archive", "Archives", "All Mail", "[Gmail]/All Mail"]
_SPAM_CANDIDATES = ["Spam", "Junk", "Junk E-mail", "[Gmail]/Spam"]
_SENT_CANDIDATES = ["Sent", "Sent Items", "Sent Messages", "[Gmail]/Sent Mail"]
_TRASH_CANDIDATES = ["Trash", "Deleted Items", "Deleted Messages", "[Gmail]/Trash"]


def _account(account_id: Optional[str]):
    return get_account(account_id) if account_id else get_default_account()


def _resolve_folder(client: IMAPClient, candidates: list[str]) -> str:
    """Return the first folder name from candidates that exists on the server."""
    existing = {f.name for f in client.list_folders()}
    for name in candidates:
        if name in existing:
            return name
    # Fallback: return first candidate and let the server error if missing
    return candidates[0]


@mcp.tool()
def list_folders(account_id: Optional[str] = None) -> list[dict]:
    """List all IMAP folders on the account.

    Returns folder name, delimiter, and attributes.
    Useful to discover folder names before move/archive operations.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        folders = client.list_folders()

    return [
        {
            "name": f.name,
            "delimiter": f.delimiter,
            "attributes": f.attributes,
            "selectable": f.is_selectable,
        }
        for f in folders
    ]


@mcp.tool()
def mark_messages(
    uids: list[int],
    folder: str = "INBOX",
    seen: Optional[bool] = None,
    flagged: Optional[bool] = None,
    answered: Optional[bool] = None,
    account_id: Optional[str] = None,
) -> dict:
    """Add or remove standard IMAP flags on messages.

    Pass `seen=True` to mark as read, `seen=False` to mark unread.
    Pass `flagged=True` to star, `flagged=False` to unstar.
    Returns count of affected messages.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        if seen is not None:
            client.set_flags(uids, folder, ["\\Seen"], add=seen)
        if flagged is not None:
            client.set_flags(uids, folder, ["\\Flagged"], add=flagged)
        if answered is not None:
            client.set_flags(uids, folder, ["\\Answered"], add=answered)

    return {"modified": len(uids), "folder": folder, "account": acc.id}


@mcp.tool()
def move_messages(
    uids: list[int],
    destination_folder: str,
    source_folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Move messages from one folder to another.

    Uses IMAP MOVE if the server supports it, otherwise COPY+DELETE.
    Returns count of moved messages.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        client.move_messages(uids, src_folder=source_folder, dst_folder=destination_folder)

    return {
        "moved": len(uids),
        "from": source_folder,
        "to": destination_folder,
        "account": acc.id,
    }


@mcp.tool()
def archive_messages(
    uids: list[int],
    source_folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Archive messages — moves them to the Archive folder.

    Automatically detects the correct archive folder name (Archive, Archives, All Mail…).
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        archive_folder = _resolve_folder(client, _ARCHIVE_CANDIDATES)
        client.move_messages(uids, src_folder=source_folder, dst_folder=archive_folder)

    return {"archived": len(uids), "folder": archive_folder, "account": acc.id}


@mcp.tool()
def delete_messages(
    uids: list[int],
    folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Permanently delete messages from a folder.

    Marks messages as \\Deleted and expunges immediately.
    WARNING: This is irreversible. Use `move_messages` to Trash for a recoverable delete.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        client.delete_messages(uids, folder)

    return {"deleted": len(uids), "folder": folder, "account": acc.id}


@mcp.tool()
def trash_messages(
    uids: list[int],
    source_folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Move messages to Trash (recoverable delete).

    Prefer this over `delete_messages` for safety.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        trash_folder = _resolve_folder(client, _TRASH_CANDIDATES)
        client.move_messages(uids, src_folder=source_folder, dst_folder=trash_folder)

    return {"trashed": len(uids), "folder": trash_folder, "account": acc.id}


@mcp.tool()
def mark_as_spam(
    uids: list[int],
    source_folder: str = "INBOX",
    account_id: Optional[str] = None,
) -> dict:
    """Report messages as spam and move them to the Spam/Junk folder.

    Automatically detects the correct spam folder name.
    """
    acc = _account(account_id)
    with IMAPClient(acc) as client:
        spam_folder = _resolve_folder(client, _SPAM_CANDIDATES)
        client.move_messages(uids, src_folder=source_folder, dst_folder=spam_folder)

    return {"reported_spam": len(uids), "folder": spam_folder, "account": acc.id}
