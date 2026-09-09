"""benching doctor — environment health checks."""
from __future__ import annotations

import typer
from rich.console import Console

from rich.table import Table
from benching.benchmark.doctor import checks

app = typer.Typer(help="Check the benching environment.", no_args_is_help=True)
console = Console()


def _checks() -> list[dict[str, object]]:
    """Collect health checks without rendering."""
    return checks()


@app.command()
def check() -> None:
    """Run environment checks and print a status table."""

    checks = _checks()
    table = Table(title="benching environment", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for check in checks:
        status = "[green]OK[/green]" if check["ok"] else "[red]MISSING[/red]"
        detail = str(check["detail"])
        table.add_row(str(check["name"]), status, detail)
    console.print(table)
    if all(check["ok"] for check in checks):
        console.print("\n[green]Ready to benchmark.[/green]")
    else:
        console.print("\n[red]Not ready; resolve the failing checks above.[/red]")
        raise typer.Exit(1)

