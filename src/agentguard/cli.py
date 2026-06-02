"""AgentGuard CLI."""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agentguard.stores.sqlite import SQLiteStore

app = typer.Typer(
    name="agentguard",
    help="Checkpoint, detect, recover — make any AI agent production-ready",
    no_args_is_help=True,
)
console = Console()


def get_store(db: str) -> SQLiteStore:
    """Get store from path."""
    return SQLiteStore(db)


@app.command()
def status(
    db: str = typer.Option("agentguard.db", "--db", "-d", help="Database path"),
) -> None:
    """Show AgentGuard status and recent checkpoints."""
    store = get_store(db)
    checkpoints = store.list(limit=10)

    if not checkpoints:
        console.print("[yellow]No checkpoints found.[/yellow]")
        return

    table = Table(title="Recent Checkpoints")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Timestamp", style="yellow")
    table.add_column("State Keys", style="magenta")

    for cp in checkpoints:
        dt = datetime.fromtimestamp(cp.timestamp)
        state_keys = ", ".join(list(cp.state.keys())[:3])
        if len(cp.state) > 3:
            state_keys += f" (+{len(cp.state) - 3} more)"

        table.add_row(
            cp.id[:12] + "...",
            cp.name,
            dt.strftime("%Y-%m-%d %H:%M:%S"),
            state_keys or "-",
        )

    console.print(table)
    console.print(f"\n[dim]Database: {db}[/dim]")


@app.command()
def list(
    db: str = typer.Option("agentguard.db", "--db", "-d", help="Database path"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of checkpoints to show"),
) -> None:
    """List all checkpoints."""
    store = get_store(db)
    checkpoints = store.list(limit=limit)

    if not checkpoints:
        console.print("[yellow]No checkpoints found.[/yellow]")
        return

    for cp in checkpoints:
        dt = datetime.fromtimestamp(cp.timestamp)
        console.print(
            f"[cyan]{cp.id[:12]}[/cyan] "
            f"[green]{cp.name}[/green] "
            f"[dim]{dt.strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
        )


@app.command()
def show(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint ID (or prefix)"),
    db: str = typer.Option("agentguard.db", "--db", "-d", help="Database path"),
) -> None:
    """Show details of a specific checkpoint."""
    store = get_store(db)

    # Try exact match first, then prefix match
    checkpoint = store.load(checkpoint_id)
    if checkpoint is None:
        # Try prefix match
        all_checkpoints = store.list(limit=1000)
        matches = [cp for cp in all_checkpoints if cp.id.startswith(checkpoint_id)]
        if len(matches) == 1:
            checkpoint = matches[0]
        elif len(matches) > 1:
            console.print(f"[yellow]Multiple matches for prefix '{checkpoint_id}':[/yellow]")
            for cp in matches[:5]:
                console.print(f"  [cyan]{cp.id}[/cyan] - {cp.name}")
            return
        else:
            console.print(f"[red]Checkpoint not found: {checkpoint_id}[/red]")
            return

    dt = datetime.fromtimestamp(checkpoint.timestamp)
    console.print(f"[bold]Checkpoint: {checkpoint.name}[/bold]\n")
    console.print(f"ID: [cyan]{checkpoint.id}[/cyan]")
    console.print(f"Timestamp: [yellow]{dt.strftime('%Y-%m-%d %H:%M:%S')}[/yellow]")
    console.print(f"Parent: [dim]{checkpoint.parent_id or 'None'}[/dim]")
    console.print("\n[bold]State:[/bold]")

    import json

    console.print_json(json.dumps(checkpoint.state, indent=2, default=str))

    if checkpoint.metadata:
        console.print("\n[bold]Metadata:[/bold]")
        console.print_json(json.dumps(checkpoint.metadata, indent=2, default=str))


@app.command()
def rollback(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint ID to rollback to"),
    db: str = typer.Option("agentguard.db", "--db", "-d", help="Database path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be restored"),
) -> None:
    """Rollback to a specific checkpoint."""
    store = get_store(db)
    checkpoint = store.load(checkpoint_id)

    if checkpoint is None:
        # Try prefix match
        all_checkpoints = store.list(limit=1000)
        matches = [cp for cp in all_checkpoints if cp.id.startswith(checkpoint_id)]
        if len(matches) == 1:
            checkpoint = matches[0]
        else:
            console.print(f"[red]Checkpoint not found: {checkpoint_id}[/red]")
            return

    if dry_run:
        console.print(f"[yellow]Would rollback to:[/yellow] {checkpoint.name}")
        console.print(f"[dim]State keys: {list(checkpoint.state.keys())}[/dim]")
    else:
        console.print(f"[green]Rolled back to:[/green] {checkpoint.name}")
        console.print(f"[dim]Checkpoint ID: {checkpoint.id}[/dim]")

        import json

        # Output state for programmatic use
        print(json.dumps(checkpoint.state, default=str))


@app.command()
def clear(
    db: str = typer.Option("agentguard.db", "--db", "-d", help="Database path"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Clear all checkpoints."""
    if not force:
        confirm = typer.confirm("Are you sure you want to clear all checkpoints?")
        if not confirm:
            raise typer.Abort()

    store = get_store(db)
    store.clear()
    console.print("[green]All checkpoints cleared.[/green]")


@app.command()
def stats(
    db: str = typer.Option("agentguard.db", "--db", "-d", help="Database path"),
) -> None:
    """Show statistics."""
    store = get_store(db)
    checkpoints = store.list(limit=10000)

    if not checkpoints:
        console.print("[yellow]No data available.[/yellow]")
        return

    # Calculate stats
    total = len(checkpoints)
    oldest = min(cp.timestamp for cp in checkpoints)
    newest = max(cp.timestamp for cp in checkpoints)

    oldest_dt = datetime.fromtimestamp(oldest)
    newest_dt = datetime.fromtimestamp(newest)

    # Count by name prefix
    name_counts: dict[str, int] = {}
    for cp in checkpoints:
        prefix = cp.name.split("_")[0] if "_" in cp.name else cp.name
        name_counts[prefix] = name_counts.get(prefix, 0) + 1

    console.print("[bold]AgentGuard Statistics[/bold]\n")
    console.print(f"Total checkpoints: [cyan]{total}[/cyan]")
    console.print(f"Oldest: [dim]{oldest_dt.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
    console.print(f"Newest: [dim]{newest_dt.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

    db_path = Path(db)
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        console.print(f"Database size: [yellow]{size_mb:.2f} MB[/yellow]")

    if name_counts:
        console.print("\n[bold]By category:[/bold]")
        for name, count in sorted(name_counts.items(), key=lambda x: -x[1])[:5]:
            console.print(f"  {name}: {count}")


@app.command()
def version() -> None:
    """Show version."""
    from agentguard import __version__

    console.print(f"AgentGuard v{__version__}")


if __name__ == "__main__":
    app()
