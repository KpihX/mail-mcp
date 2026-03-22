# mail-mcp

**Generic IMAP+SMTP MCP server for AI agents.**

Connect any email account to any AI agent (Claude, Gemini, Codex, Copilot…).
Intent-first design: high-level tools that match real user workflows, backed by a clean IMAP/SMTP core.

```
Problem: AI agents have no native email access.
Why: IMAP+SMTP are universal, server-agnostic, and require no OAuth2 dance.
How: FastMCP tools layer, pure stdlib SMTP, imapclient for IMAP, secrets via bw-env.
```

---

## Architecture

```
mail_mcp/
├── config.yaml          # Non-sensitive settings (hosts, ports, env var names)
├── config.py            # @lru_cache loader + 3-tier secret resolution
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
└── cli.py               # Typer+Rich admin: serve, status, inbox, folders, accounts
```

### Secret resolution (3 tiers)

```
1. Process env     → fastest (already injected by shell or MCP host)
2. bw-env login    → zsh -l -c 'printf "%s" "${VAR}"'  (Bitwarden GLOBAL_ENV_VARS)
3. local .env      → dev override only, never committed
```

---

## Supported accounts

| Account | IMAP | SMTP | Server |
|---------|------|------|--------|
| Polytechnique (X) | `webmail.polytechnique.fr:993` TLS | `:587` STARTTLS | Zimbra |

More accounts: add an entry in `config.yaml` — no code change needed.

---

## Quick start

```bash
# Install (editable)
uv tool install --editable .

# Check credentials
mail-mcp status

# List folders
mail-mcp folders

# Show inbox
mail-mcp inbox -n 5

# Start MCP server
mail-mcp serve
```

---

## MCP agent registration

### Claude Code (`~/.claude.json`)

```json
"mail-mcp": {
  "command": "zsh",
  "args": ["-l", "-c", "/home/kpihx/.local/bin/mail-mcp serve"]
}
```

### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.mail_mcp]
command = "zsh"
args = ["-l", "-c", "/home/kpihx/.local/bin/mail-mcp serve"]
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
| `mark_messages` | Seen / flagged / answered flags |
| `move_messages` | Move UIDs to folder |
| `archive_messages` | Move to Archive |
| `trash_messages` | Move to Trash |
| `delete_messages` | Permanent delete + expunge |
| `mark_as_spam` | Move to Spam/Junk |

---

## Security

- Credentials are **never** stored in `config.yaml` — only env var names.
- Secrets live in Bitwarden (`GLOBAL_ENV_VARS`) and are injected via `bw-env` / login shell.
- `.env` is gitignored and for local dev only.
- No OAuth2, no refresh token storage — IMAP password auth via TLS only.

---

## Roadmap (v0.2+)

- Multi-account support with account selector
- CalDAV / CardDAV integration (Zimbra has both)
- IDLE push notifications
- Attachment download tool
- Additional email providers (Gmail OAuth2, Outlook EWS)
