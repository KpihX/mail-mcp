# CHANGELOG — mail-mcp

## [0.2.0] — 2026-03-22

- [x] Triple admin surface: CLI (`mail-admin`), HTTP admin routes, Telegram bot
- [x] `mail-admin` CLI: `status`, `help`, `logs`, `credentials set/unset` (Rich+Typer)
- [x] HTTP admin routes: `/health`, `/admin/status`, `/admin/help`, `/admin/logs`, `POST /admin/credentials/set`, `POST /admin/credentials/unset`
- [x] Telegram long-poll bot: in-process daemon thread; commands `/start`, `/help`, `/status`, `/health`, `/urls`, `/logs`, `/credentials_set`, `/credentials_unset`, `/restart`
- [x] Token: `TELEGRAM_MAIL_HOMELAB_TOKEN` / auth gate: `TELEGRAM_CHAT_IDS`
- [x] `daemon.py`: PID file lifecycle (`write_pid`, `read_pid`, `clear_pid`, `is_running`)
- [x] Admin env file (`ADMIN_ENV_PATH`): persistent credential overrides without redeployment — `/data/mail-admin.env` in Docker (volume-mounted), `~/.mcps/mail/mail-admin.env` locally
- [x] `_load_nonempty_dotenv`: silently ignores blank placeholder lines to avoid clobbering injected secrets
- [x] `APP_VERSION` from `importlib.metadata` with fallback
- [x] Streamable-HTTP transport via `mcp.http_app()` — homelab at `mail.kpihx-labs.com:8094`
- [x] Docker volume `mail_mcp_data:/data` for persistent admin env across restarts
- [x] GitLab CI: validate (smoke test) + deploy_homelab (tag: homelab, only: master)
- [x] Dual transport: HTTP homelab + stdio fallback registered in Claude, Codex, Vibe, Gemini, Copilot

## [0.1.0] — 2026-03-22

- [x] Initial release — generic IMAP+SMTP MCP server
- [x] Zimbra / Polytechnique (X) as first account (`webmail.polytechnique.fr`)
- [x] IMAP core: connection pooling, search, fetch summaries/full messages, flag ops, move/delete/expunge
- [x] SMTP core: send, reply (with proper In-Reply-To/References), forward, draft (IMAP APPEND)
- [x] Intent-first MCP tools: `mail_guide`, `check_inbox`, `daily_digest`, `list_messages`, `get_message`, `search_messages`, `find_unread`, `get_thread`
- [x] Compose tools: `send_message`, `reply_message`, `forward_message`, `save_draft`
- [x] Management tools: `list_folders`, `mark_messages`, `move_messages`, `archive_messages`, `delete_messages`, `trash_messages`, `mark_as_spam`
- [x] CLI admin: `mail-mcp serve`, `status`, `inbox`, `folders`, `accounts`
- [x] Secret resolution via bw-env (`X_LOGIN`/`X_PASS` in GLOBAL_ENV_VARS)
- [x] Config: `config.yaml` + 3-tier resolution (process env → login shell → .env)
- [x] Unit tests for config and models
