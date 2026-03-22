"""
Telegram admin bridge for mail-mcp.

Runs as an in-process background poller inside the HTTP service so credential
updates and operational actions can affect the live server directly.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import httpx

from .service import (
    admin_help_text,
    get_accounts_status,
    get_logs_text,
    health_summary,
    set_account_credentials,
    status_summary_text,
    unset_account_credentials,
    urls_summary,
)
from ..config import TELEGRAM_CHAT_IDS, TELEGRAM_MAIL_HOMELAB_TOKEN


_log = logging.getLogger("mail_mcp.admin.telegram")
_poller_started = False
_restart_callback: Callable[[], None] | None = None
_poller_thread: threading.Thread | None = None
_poller_state: dict[str, object | None] = {
    "started_at": None,
    "last_poll_at": None,
    "last_success_at": None,
    "last_update_id": None,
    "last_chat_id": None,
    "last_command": None,
    "last_reply_preview": None,
    "last_error": None,
}


class TelegramAdminBot:
    def __init__(self, token: str, allowed_chat_ids: tuple[str, ...]) -> None:
        self.token = token
        self.allowed_chat_ids = {str(chat_id) for chat_id in allowed_chat_ids}
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0

    def run_forever(self) -> None:
        _poller_state["started_at"] = int(time.time())
        _log.info("Telegram admin poller started for %d allowed chats.", len(self.allowed_chat_ids))
        with httpx.Client(timeout=35.0) as client:
            while True:
                try:
                    _poller_state["last_poll_at"] = int(time.time())
                    response = client.get(
                        f"{self.base_url}/getUpdates",
                        params={"timeout": 25, "offset": self.offset},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    _poller_state["last_success_at"] = int(time.time())
                    _poller_state["last_error"] = None
                    for update in payload.get("result", []):
                        self.offset = max(self.offset, int(update["update_id"]) + 1)
                        _poller_state["last_update_id"] = int(update["update_id"])
                        self._handle_update(client, update)
                except Exception as exc:  # noqa: BLE001
                    _poller_state["last_error"] = str(exc)
                    _log.exception("Telegram poll loop error: %s", exc)
                    time.sleep(5)

    def _handle_update(self, client: httpx.Client, update: dict) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = (message.get("text") or "").strip()
        _poller_state["last_chat_id"] = chat_id or None
        if not text.startswith("/"):
            return
        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            _log.warning("Rejected Telegram command from unauthorized chat %s", chat_id)
            self._send_message(client, chat_id, "Unauthorized chat.")
            return

        command, *args = text.split()
        command = command.split("@", 1)[0].lower()
        _poller_state["last_command"] = command
        _log.info("Telegram command received: chat=%s command=%s args=%s", chat_id, command, args)
        try:
            reply = self._dispatch(command, args)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Telegram command failed: %s", exc)
            reply = f"Command failed: {exc}"
        _poller_state["last_reply_preview"] = reply[:120]
        self._send_message(client, chat_id, reply)
        _log.info("Telegram reply sent: chat=%s preview=%r", chat_id, reply[:120])

    def _dispatch(self, command: str, args: list[str]) -> str:
        if command in {"/start", "/help"}:
            return admin_help_text()
        if command == "/status":
            account_id = args[0] if args else None
            accounts = get_accounts_status()
            if account_id:
                accounts = [a for a in accounts if a["id"] == account_id]
                if not accounts:
                    return f"Account not found: {account_id!r}"
            lines = []
            for a in accounts:
                default_marker = " [default]" if a["default"] else ""
                lines.append(f"Account: {a['id']}{default_marker} ({a['label']})")
                lines.append(f"  {a['login_env']}: {'set' if a['login_present'] else 'MISSING'} [{a['login_source']}]")
                lines.append(f"  {a['password_env']}: {'set' if a['password_present'] else 'MISSING'} [{a['password_source']}]")
            return "\n".join(lines) if lines else "No accounts configured."
        if command == "/health":
            return health_summary()
        if command == "/urls":
            return urls_summary()
        if command == "/logs":
            lines = int(args[0]) if args else 40
            return get_logs_text(lines)
        if command == "/credentials_set":
            # Usage: /credentials_set <account_id> <login> <password>
            if len(args) < 3:
                return "Usage: /credentials_set <account_id> <login> <password>"
            account_id, login, password = args[0], args[1], args[2]
            try:
                result = set_account_credentials(account_id, login, password)
                return (
                    f"Credentials set for {account_id}\n"
                    f"  {result['login_env']}: {result['login_masked']}\n"
                    f"  {result['password_env']}: {result['password_masked']}"
                )
            except ValueError as exc:
                return str(exc)
        if command == "/credentials_unset":
            # Usage: /credentials_unset <account_id>
            if not args:
                return "Usage: /credentials_unset <account_id>"
            account_id = args[0]
            try:
                result = unset_account_credentials(account_id)
                return (
                    f"Credentials cleared for {account_id}\n"
                    f"  {result['login_env']}: cleared\n"
                    f"  {result['password_env']}: cleared"
                )
            except ValueError as exc:
                return str(exc)
        if command == "/restart":
            if _restart_callback is None:
                return "Restart callback is not configured."
            threading.Thread(target=_restart_callback, daemon=True).start()
            return "mail-mcp restart requested."
        return "Unknown command. Use /help."

    def _send_message(self, client: httpx.Client, chat_id: str, text: str) -> None:
        client.post(
            f"{self.base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
        ).raise_for_status()


def start_telegram_admin(restart_callback: Callable[[], None]) -> None:
    global _poller_started, _restart_callback, _poller_thread
    if _poller_started:
        return
    if not TELEGRAM_MAIL_HOMELAB_TOKEN:
        _log.info("Telegram admin disabled: token missing.")
        return
    if not TELEGRAM_CHAT_IDS:
        _log.warning("Telegram admin disabled: allowed chat IDs missing.")
        return
    _restart_callback = restart_callback
    bot = TelegramAdminBot(
        token=TELEGRAM_MAIL_HOMELAB_TOKEN,
        allowed_chat_ids=TELEGRAM_CHAT_IDS,
    )
    thread = threading.Thread(target=bot.run_forever, daemon=True, name="mail-mcp-telegram-admin")
    thread.start()
    _poller_thread = thread
    _poller_started = True


def telegram_admin_enabled() -> bool:
    return bool(TELEGRAM_MAIL_HOMELAB_TOKEN and TELEGRAM_CHAT_IDS)


def telegram_admin_runtime_status() -> dict[str, object | None]:
    return {
        "enabled": telegram_admin_enabled(),
        "started": _poller_started,
        "thread_alive": bool(_poller_thread and _poller_thread.is_alive()),
        "allowed_chat_count": len(TELEGRAM_CHAT_IDS),
        "allowed_chat_ids": list(TELEGRAM_CHAT_IDS),
        **_poller_state,
    }
