"""benching runs — inspect benchmark run directories."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from benchmark._paths import ROOT, RUNS

app = typer.Typer(help="Inspect past benchmark runs.", no_args_is_help=True)
console = Console()


def _all_run_dirs() -> list[Path]:
    if not RUNS.is_dir():
        return []
    candidates = [path for path in RUNS.iterdir() if path.is_dir() and (path / "run.json").is_file()]
    return sorted(candidates, key=lambda path: path.name, reverse=True)


def _run_json(directory: Path) -> dict[str, Any] | None:
    try:
        return json.loads((directory / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _status(directory: Path) -> str:
    try:
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        return str(status.get("status", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


def _resolve_run(run_ref: str) -> Path:
    """Resolve a run-id prefix or 'latest' to a run directory."""
    directories = _all_run_dirs()
    if not directories:
        raise typer.BadParameter("no runs found under runs/")
    if run_ref == "latest":
        return directories[0]
    matches = [directory for directory in directories if directory.name.startswith(run_ref)]
    if not matches:
        raise typer.BadParameter(f"no run matches {run_ref!r}; see `benching runs`")
    if len(matches) > 1:
        names = "\n".join(directory.name for directory in matches[:10])
        raise typer.BadParameter(f"run reference {run_ref!r} is ambiguous:\n{names}")
    return matches[0]


def _format_age(path: Path) -> str:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return "?"
    delta = datetime.now(timezone.utc) - modified
    if delta.total_seconds() < 90:
        return "just now"
    if delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() // 60)}m ago"
    if delta.total_seconds() < 86400:
        return f"{int(delta.total_seconds() // 3600)}h ago"
    return f"{int(delta.total_seconds() // 86400)}d ago"


@app.command()
def list() -> None:
    """List all benchmark runs, newest first."""
    directories = _all_run_dirs()
    if not directories:
        console.print("[yellow]No runs yet.[/yellow]")
        return
    table = Table(title="Runs", show_header=True, header_style="bold")
    table.add_column("RUN ID", style="bold")
    table.add_column("PROVIDER")
    table.add_column("MODE")
    table.add_column("BENCHMARK")
    table.add_column("STATUS")
    table.add_column("AGE")
    for directory in directories:
        run = _run_json(directory)
        name = directory.name
        provider = str((run or {}).get("provider", "?"))
        mode = "smoke" if "-smoke-" in name else ("full" if "-full-" in name else "?")
        benchmark = f"{run.get('benchmark', '?')} {run.get('benchmark_version', '')}".strip() if run else "?"
        table.add_row(name, provider, mode, benchmark, _status(directory), _format_age(directory))
    console.print(table)


@app.command("show")
def show(run_id: str) -> None:
    """Show full configuration of one run (by id, id prefix, or 'latest')."""
    directory = _resolve_run(run_id)
    run = _run_json(directory)
    if run is None:
        raise typer.BadParameter(f"run.json unreadable in {directory}")
    from rich.console import Console
    from rich.panel import Panel

    lines = [
        f"[bold]Run:[/bold] {run.get('run_id')}",
        f"[bold]Status:[/bold] {_status(directory)}",
        f"[bold]Benchmark:[/bold] {run.get('benchmark')} {run.get('benchmark_version', '')}".strip(),
        f"[bold]Provider:[/bold] {run.get('provider')}",
        f"[bold]Model:[/bold] {run.get('benchmark_model')} (api {run.get('api_model')})",
        f"[bold]Tasks:[/bold] {run.get('task_count')}",
        f"[bold]Concurrency:[/bold] {run.get('concurrency')}  [bold]Trials:[/bold] {run.get('trials')}",
        f"[bold]Created:[/bold] {run.get('created_at_utc')}",
        f"[bold]Directory:[/bold] {directory}",
    ]
    console.print(Panel("\n".join(lines), title="Run", expand=False))
    fingerprint = run.get("environment_fingerprint")
    if fingerprint:
        console.print(f"Environment fingerprint: [cyan]{fingerprint}[/cyan]")


@app.command()
def latest() -> None:
    """Show the most recent run's id."""
    directory = _resolve_run("latest")
    run = _run_json(directory) or {}
    console.print(f"{run.get('run_id', directory.name)}")
