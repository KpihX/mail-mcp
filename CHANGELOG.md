# CHANGELOG — mail-mcp

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
