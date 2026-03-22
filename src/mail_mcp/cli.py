"""mail-mcp CLI — admin commands via Typer + Rich."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mail_mcp.config import get_config, get_default_account, get_account
from mail_mcp.core.imap_client import IMAPClient

app = typer.Typer(
    name="mail-mcp",
    help="mail-mcp admin CLI — manage accounts, test connections, serve MCP.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def serve() -> None:
    """Start the MCP server (stdio transport)."""
    from mail_mcp.server import serve as _serve
    _serve()


@app.command()
def status(account_id: Optional[str] = typer.Option(None, "--account", "-a", help="Account ID")) -> None:
    """Show connection status and inbox stats."""
    config = get_config()
    acc = get_account(account_id) if account_id else get_default_account()

    console.print(f"\n[bold]mail-mcp[/bold] — account: [cyan]{acc.id}[/cyan] ({acc.label})")
    console.print(f"  IMAP: [dim]{acc.imap.host}:{acc.imap.port}[/dim] {'TLS' if acc.imap.tls else 'STARTTLS'}")
    console.print(f"  SMTP: [dim]{acc.smtp.host}:{acc.smtp.port}[/dim] {'STARTTLS' if acc.smtp.starttls else 'TLS'}")
    console.print(f"  Login: [dim]{acc.username or '[NOT RESOLVED]'}[/dim]\n")

    if not acc.username or not acc.password:
        console.print("[red]Credentials not resolved — check bw-env or .env file.[/red]")
        raise typer.Exit(1)

    console.print("Connecting...", end=" ")
    try:
        with IMAPClient(acc) as client:
            inbox = client.get_folder_status("INBOX")
        console.print("[green]OK[/green]")
        console.print(f"  INBOX: {inbox.message_count} messages, {inbox.unseen_count} unread")
    except Exception as e:
        console.print(f"[red]FAILED[/red]\n  {e}")
        raise typer.Exit(1)


@app.command()
def folders(account_id: Optional[str] = typer.Option(None, "--account", "-a")) -> None:
    """List all IMAP folders."""
    acc = get_account(account_id) if account_id else get_default_account()

    with IMAPClient(acc) as client:
        folder_list = client.list_folders()

    table = Table(title=f"Folders — {acc.id}", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Attributes", style="dim")
    table.add_column("Selectable")

    for f in sorted(folder_list, key=lambda x: x.name):
        table.add_row(
            f.name,
            ", ".join(f.attributes),
            "[green]yes[/green]" if f.is_selectable else "[red]no[/red]",
        )

    console.print(table)


@app.command()
def inbox(
    limit: int = typer.Option(10, "--limit", "-n"),
    account_id: Optional[str] = typer.Option(None, "--account", "-a"),
) -> None:
    """Show recent unread messages in INBOX."""
    from mail_mcp.core.models import SearchCriteria

    acc = get_account(account_id) if account_id else get_default_account()

    with IMAPClient(acc) as client:
        uids = client.search(SearchCriteria(folder="INBOX", unseen_only=True, limit=limit))
        summaries = client.fetch_summaries(uids, "INBOX")

    if not summaries:
        console.print("[dim]No unread messages.[/dim]")
        return

    table = Table(title=f"Inbox (unread) — {acc.id}", show_header=True)
    table.add_column("UID", style="dim", width=6)
    table.add_column("From", style="cyan", width=30)
    table.add_column("Subject", width=50)
    table.add_column("Date", style="dim", width=20)

    for m in summaries:
        table.add_row(
            str(m.uid),
            m.sender.email if m.sender else "",
            m.subject,
            m.date.strftime("%Y-%m-%d %H:%M") if m.date else "",
        )

    console.print(table)


@app.command()
def accounts() -> None:
    """List all configured accounts."""
    config = get_config()
    table = Table(title="Configured accounts", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Label")
    table.add_column("IMAP host")
    table.add_column("SMTP host")
    table.add_column("Default")

    for a in config.accounts:
        table.add_row(
            a.id,
            a.label,
            f"{a.imap.host}:{a.imap.port}",
            f"{a.smtp.host}:{a.smtp.port}",
            "[green]yes[/green]" if a.default else "",
        )

    console.print(table)


if __name__ == "__main__":
    app()
