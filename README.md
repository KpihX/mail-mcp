# mail-mcp

**Generic IMAP+SMTP MCP server for AI agents — v0.2.0**

Connect any email account to any AI agent (Claude, Gemini, Codex, Copilot, Vibe…).
Intent-first design: high-level tools matching real user workflows, backed by a clean IMAP/SMTP core
and a full **triple admin surface** (CLI + HTTP + Telegram).

```
Problem: AI agents have no native email access.
Why:     IMAP+SMTP are universal, server-agnostic, no OAuth2 dance required.
How:     FastMCP tools layer, pure stdlib SMTP, imapclient for IMAP, bw-env secrets.
Admin:   mail-admin CLI  +  /admin/* HTTP routes  +  Telegram bot  +  SSH exec.
```

**Repos:** [GitHub](https://github.com/KpihX/mail-mcp) · [GitLab](https://gitlab.com/kpihx-labs/mail-mcp)

---

## Architecture

```
mail_mcp/
├── config.yaml          # Non-sensitive settings (hosts, ports, env var names)
├── config.py            # @lru_cache loader + 3-tier secret resolution + admin env
│
├── admin/
│   ├── service.py       # Shared backend: status, credentials CRUD, logs, summaries
│   ├── cli.py           # mail-admin — Typer+Rich admin CLI
│   └── telegram.py      # Telegram long-poll bot (in-process thread)
│
├── core/
│   ├── models.py        # Pydantic: Message, MessageSummary, Folder, Address…
│   ├── imap_client.py   # IMAPClient context-manager — search, fetch, flags, move
│   └── smtp_client.py   # SMTPClient — send, reply, forward, draft
│
├── tools/
│   ├── guide.py         # mail_guide() — agent orientation entry point
│   ├── read.py          # check_inbox, daily_digest, search_messages, get_thread…
│   ├── compose.py       # send_message, reply_message, forward_message, save_draft
│   └── manage.py        # list_folders, mark_messages, move/archive/delete/spam
│
├── server.py            # FastMCP root — mounts all sub-MCPs
├── http_app.py          # Starlette app: MCP + /health + /admin/* routes
├── daemon.py            # PID file lifecycle
└── cli.py               # Typer CLI: serve, serve-http, stop, status, inbox, folders
```

### Secret resolution (3 tiers)

```
1. Admin env file  → /data/mail-admin.env  (Docker volume, persistent credential overrides)
2. Process env     → fastest (shell injection or MCP host)
3. bw-env login    → zsh -l -c 'printf "%s" "${VAR}"'  (Bitwarden GLOBAL_ENV_VARS)
```

---

## Transports

| Transport | URL / Command | Description |
|-----------|---------------|-------------|
| **HTTP (homelab)** | `https://mail.kpihx-labs.com/mcp` | Streamable-HTTP — production, always-on |
| **stdio (fallback)** | `mail-mcp serve` | Direct process — local dev or when HTTP down |

---

## Supported accounts

| Account | IMAP | SMTP | Server |
|---------|------|------|--------|
| Polytechnique (X) | `webmail.polytechnique.fr:993` TLS | `:587` STARTTLS | Zimbra |

More accounts: add an entry in `config.yaml` — no code change needed.

---

## Quick start

```bash
# Install (editable for live dev)
uv tool install --editable .

# Admin CLI
mail-admin status          # credential status table
mail-admin logs 20         # last 20 log lines
mail-admin credentials set poly <login> <pass>   # live update without restart
mail-admin help            # full capability map

# MCP stdio server
mail-mcp serve

# MCP HTTP server (port 8094)
mail-mcp serve-http
```

---

## Admin surfaces

### 1. CLI — `mail-admin`

```
mail-admin status [--account <id>]   # Rich table: env var, value (masked), source
mail-admin logs [N]                  # tail last N lines (default 40)
mail-admin credentials set <id> <login> <pass>
mail-admin credentials unset <id>
mail-admin help                      # full capability map
```

### 2. HTTP routes

| Route | Method | Description |
|-------|--------|-------------|
| `/health` | GET | Readiness probe — auth presence per account |
| `/admin/status` | GET | Full status: pid, transport, Telegram runtime, credentials |
| `/admin/help` | GET | Full capability map (CLI / HTTP / Telegram / SSH) |
| `/admin/logs?lines=40` | GET | Tail of the admin log |
| `/admin/credentials/set` | POST | Set `{account_id, login, password}` |
| `/admin/credentials/unset` | POST | Clear credentials for `{account_id}` |
| `/mcp` | GET/POST | Streamable-HTTP MCP transport |

### 3. Telegram bot

Token env: `TELEGRAM_MAIL_HOMELAB_TOKEN` — auth gate: `TELEGRAM_CHAT_IDS`

| Command | Args | Effect |
|---------|------|--------|
| `/start` `/help` | — | Full capability map |
| `/status` | `[account_id]` | Credential status |
| `/health` | — | Quick health summary |
| `/urls` | — | Transport URLs |
| `/logs` | `[N]` | Last N log lines |
| `/credentials_set` | `<id> <login> <pass>` | Live credential update |
| `/credentials_unset` | `<id>` | Clear credentials |
| `/restart` | — | Graceful service restart |

### 4. SSH exec

```bash
docker compose exec -T mail-mcp mail-admin status
docker compose logs --tail=100 mail-mcp
```

---

## MCP agent registration

### Claude Code (`~/.claude.json`)

```json
"mail-mcp": {
  "url": "https://mail.kpihx-labs.com/mcp"
},
"mail-mcp--fallback": {
  "command": "zsh",
  "args": ["-l", "-c", "/home/kpihx/.local/bin/mail-mcp serve"]
}
```

### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.mail_mcp]
url = "https://mail.kpihx-labs.com/mcp"

[mcp_servers.mail_mcp_fallback]
command = "zsh"
args = ["-l", "-c", "/home/kpihx/.local/bin/mail-mcp serve"]
```

### Vibe/Mistral (`~/.vibe/config.toml`)

```toml
[[mcp_servers]]
name = "mail"
transport = "http"
url = "https://mail.kpihx-labs.com/mcp"

[[mcp_servers]]
name = "mail_fallback"
transport = "stdio"
command = "zsh"
args = ["-l", "-c", "/home/kpihx/.local/bin/mail-mcp serve"]
```

### Gemini (`~/.gemini/settings.json`)

```json
"mcpServers": {
  "mail-mcp": { "url": "https://mail.kpihx-labs.com/mcp" },
  "mail-mcp--fallback": {
    "command": "zsh",
    "args": ["-l", "-c", "/home/kpihx/.local/bin/mail-mcp serve"]
  }
}
```

---

## Tool reference

| Tool | Intent |
|------|--------|
| `mail_guide` | Agent orientation — start here |
| `check_inbox` | Unread count + last N summaries |
| `daily_digest` | Structured morning overview |
| `list_messages` | Browse a folder |
| `get_message` | Full body by UID |
| `search_messages` | Flexible search (query, sender, date, flags) |
| `find_unread` | Unread shortcut |
| `get_thread` | Full thread by Message-ID |
| `send_message` | New email |
| `reply_message` | Reply by UID |
| `forward_message` | Forward by UID |
| `save_draft` | Draft to Drafts folder |
| `list_folders` | All IMAP folders |
| `list_labels` | Alias for `list_folders` |
| `create_folder` | Create IMAP folder |
| `rename_folder` | Rename IMAP folder |
| `delete_folder` | Delete IMAP folder |
| `mark_messages` | Seen / flagged / answered flags |
| `move_messages` | Move UIDs to folder |
| `archive_messages` | Move to Archive |
| `trash_messages` | Move to Trash |
| `delete_messages` | Permanent delete + expunge |
| `mark_as_spam` | Move to Spam/Junk |
| `download_attachment` | Download to file (default) or ingest as Base64 (`ingest_base64=True`) |
| `set_labels` | Alias for `move_messages` |

---

## Security

- Credentials are **never** stored in `config.yaml` — only env var names.
- Secrets live in Bitwarden (`GLOBAL_ENV_VARS`) and are injected via `bw-env` / login shell.
- Admin credential overrides persist in `/data/mail-admin.env` (Docker volume) — never committed.
- No OAuth2, no refresh token storage — IMAP password auth via TLS only.

---

## Deployment (Docker / homelab)

See `deploy/` for `docker-compose.yml` and `.env.example`.

```bash
# Required env vars
X_LOGIN=your_imap_username
X_PASS=your_imap_password
TELEGRAM_MAIL_HOMELAB_TOKEN=<bot_token>    # optional
TELEGRAM_CHAT_IDS=<comma,separated,ids>    # optional
MAIL_MCP_ADMIN_ENV_FILE=/data/mail-admin.env
```

GitLab CI auto-deploys `master` to the homelab runner via `docker compose up -d --build`.
