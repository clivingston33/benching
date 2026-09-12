"""benching doctor — environment health checks.

Thin presentation over :mod:`benching.benchmark.doctor`: core produces
structured check results, this module only formats them.
"""
from __future__ import annotations

import typer
from rich.console import Console

from rich.table import Table
from benching.benchmark.doctor import checks

app = typer.Typer(help="Check the benching environment.", no_args_is_help=False)
console = Console()


def _checks() -> list[dict[str, object]]:
    """Collect health checks without rendering."""
    return checks()


def render_checks(results: list[dict[str, object]]) -> bool:
    """Render structured check results; return True when all pass."""
    table = Table(title="benching environment", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for item in results:
        status = "[green]OK[/green]" if item["ok"] else "[red]MISSING[/red]"
        table.add_row(str(item["name"]), status, str(item["detail"]))
    console.print(table)
    ready = all(item["ok"] for item in results)
    if ready:
        console.print("\n[green]Ready to benchmark.[/green]")
    else:
        console.print("\n[red]Not ready; resolve the failing checks above.[/red]")
    return ready


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Bare `benching doctor` runs checks (M5: documented invocation works)."""
    if ctx.invoked_subcommand is None:
        check()


@app.command()
def check() -> None:
    """Run environment checks and print a status table."""
    if not render_checks(_checks()):
        raise typer.Exit(1)
