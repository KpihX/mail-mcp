"""
mail-admin — Admin CLI for the mail-mcp IMAP+SMTP server.

Manage per-account IMAP/SMTP credentials stored in the admin env file
without going through an LLM. All writes use python-dotenv's set_key()
which safely creates or updates a single line without touching the rest.

Usage examples:
    mail-admin status
    mail-admin status --account poly
    mail-admin credentials set --account poly --login user@x.com
    mail-admin credentials unset --account poly
    mail-admin logs 80
"""
from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from .service import (
    admin_help_text,
    get_accounts_status,
    get_logs_text,
    set_account_credentials,
    unset_account_credentials,
)
from ..config import ADMIN_ENV_PATH


# ---------------------------------------------------------------------------
# Typer app setup
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="mail-admin",
    help="Admin CLI — manage mail-mcp email credentials and account connections.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

credentials_app = typer.Typer(
    help="Manage IMAP/SMTP credentials stored in the admin env file.",
    no_args_is_help=True,
)
app.add_typer(credentials_app, name="credentials")

console = Console()
err = Console(stderr=True)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@app.command()
def status(
    account_id: Annotated[
        Optional[str],
        typer.Option("--account", "-a", help="Account ID to show. Omit for all accounts."),
    ] = None,
) -> None:
    """Show credential resolution status for configured accounts."""
    accounts = get_accounts_status()
    if account_id:
        accounts = [a for a in accounts if a["id"] == account_id]
        if not accounts:
            err.print(f"[red]Account not found:[/red] {account_id!r}")
            raise typer.Exit(1)

    table = Table(title="mail-admin status", box=box.ROUNDED, show_lines=True, highlight=True)
    table.add_column("Account", style="bold cyan", no_wrap=True)
    table.add_column("Variable", style="cyan")
    table.add_column("Status")
    table.add_column("Value (masked)")
    table.add_column("Source")

    for a in accounts:
        default_marker = " [default]" if a["default"] else ""
        account_label = f"{a['id']}{default_marker}\n[dim]{a['label']}[/dim]"
        table.add_row(
            account_label,
            a["login_env"],
            "[green]✓ set[/green]" if a["login_present"] else "[red]✗ missing[/red]",
            a["login_masked"],
            a["login_source"],
        )
        table.add_row(
            "",
            a["password_env"],
            "[green]✓ set[/green]" if a["password_present"] else "[red]✗ missing[/red]",
            a["password_masked"],
            a["password_source"],
        )

    console.print()
    console.print(f"[dim]Admin env path:[/dim] {ADMIN_ENV_PATH}")
    console.print(table)


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


@app.command("help")
def help_command() -> None:
    """Show the shared admin capability summary (CLI, HTTP, SSH)."""
    console.print(admin_help_text(), markup=False)


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@app.command("logs")
def logs(
    lines: Annotated[Optional[int], typer.Argument(help="Number of lines to display.")] = 40,
) -> None:
    """Show the admin log output."""
    console.print(get_logs_text(lines or 40))


# ---------------------------------------------------------------------------
# credentials set / unset
# ---------------------------------------------------------------------------


@credentials_app.command("set")
def credentials_set(
    account_id: Annotated[
        str,
        typer.Option("--account", "-a", help="Account ID (from config.yaml)."),
    ] = "poly",
    login: Annotated[
        Optional[str],
        typer.Option("--login", "-l", help="IMAP/SMTP login username. Prompted if omitted."),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option("--password", "-p", help="IMAP/SMTP password. Prompted if omitted."),
    ] = None,
) -> None:
    """Set IMAP/SMTP credentials for an account in the admin env file."""
    if not login:
        login = typer.prompt("Login (IMAP/SMTP username)")
    if not password:
        password = typer.prompt("Password", hide_input=True)

    result = set_account_credentials(account_id, login, password)
    console.print(
        f"[green]✓[/green] Credentials set for account [cyan]{account_id}[/cyan] "
        f"in [dim]{result['env_path']}[/dim]"
    )
    console.print(f"  [dim]{result['login_env']}:[/dim] {result['login_masked']}")
    console.print(f"  [dim]{result['password_env']}:[/dim] {result['password_masked']}")


@credentials_app.command("unset")
def credentials_unset(
    account_id: Annotated[
        str,
        typer.Option("--account", "-a", help="Account ID (from config.yaml)."),
    ] = "poly",
) -> None:
    """Clear IMAP/SMTP credentials for an account from the admin env file."""
    result = unset_account_credentials(account_id)
    console.print(
        f"[green]✓[/green] Credentials cleared for account [cyan]{account_id}[/cyan] "
        f"in [dim]{result['env_path']}[/dim]"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
