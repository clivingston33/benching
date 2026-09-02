"""benching runs — inspect benchmark run directories."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from benchmark._paths import RUNS
from benchmark.status import scan_harbor_results

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


def _duration_seconds(directory: Path) -> float | None:
    """Best-effort run duration from created_at_utc to status update."""
    run = _run_json(directory) or {}
    created = run.get("created_at_utc")
    status = None
    try:
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    updated = (status or {}).get("updated_at_utc") if isinstance(status, dict) else None
    if not created or not updated:
        return None
    try:
        start = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        return max(0.0, (end - start).total_seconds())
    except ValueError:
        return None


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _task_counts(directory: Path) -> dict[str, int]:
    """Per-task pass/fail from harbor results (empty when none present)."""
    counts = {"passed": 0, "failed": 0, "timed_out": 0}
    for result in scan_harbor_results(directory / "harbor").values():
        outcome = result.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
    return counts


@app.command("list")
def list(
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider name"),
    status: str | None = typer.Option(None, "--status", help="Filter by run status (e.g. completed, failed, running)"),
) -> None:
    """List benchmark runs, newest first, with optional filters."""
    directories = _all_run_dirs()
    if provider:
        directories = [d for d in directories if str((_run_json(d) or {}).get("provider", "")) == provider]
    if status:
        directories = [d for d in directories if _status(d) == status]
    if not directories:
        console.print("[yellow]No runs match.[/yellow]")
        return
    table = Table(title="Runs", show_header=True, header_style="bold", box=None)
    table.add_column("RUN ID", style="bold", no_wrap=True, overflow="ellipsis", min_width=24)
    table.add_column("PROVIDER", no_wrap=True)
    table.add_column("MODE", no_wrap=True)
    table.add_column("BENCHMARK", no_wrap=True, overflow="ellipsis")
    table.add_column("STATUS", no_wrap=True)
    table.add_column("PASSED", justify="right", no_wrap=True)
    table.add_column("FAILED", justify="right", no_wrap=True)
    table.add_column("DURATION", justify="right", no_wrap=True)
    table.add_column("AGE", no_wrap=True)
    for directory in directories:
        run = _run_json(directory)
        name = directory.name
        provider_name = str((run or {}).get("provider", "?"))
        mode = "smoke" if "-smoke-" in name else ("full" if "-full-" in name else "?")
        benchmark = f"{run.get('benchmark', '?')} {run.get('benchmark_version', '')}".strip() if run else "?"
        counts = _task_counts(directory)
        passed_col = str(counts["passed"]) if counts["passed"] or counts["failed"] or counts["timed_out"] else "—"
        failed_col = str(counts["failed"] + counts["timed_out"]) if counts["passed"] or counts["failed"] or counts["timed_out"] else "—"
        table.add_row(
            name,
            provider_name,
            mode,
            benchmark,
            _status(directory),
            passed_col,
            failed_col,
            _fmt_duration(_duration_seconds(directory)),
            _format_age(directory),
        )
    console.print(table)


@app.command("show")
def show(run_id: str) -> None:
    """Show full configuration of one run (by id, id prefix, or 'latest')."""
    directory = _resolve_run(run_id)
    run = _run_json(directory)
    if run is None:
        raise typer.BadParameter(f"run.json unreadable in {directory}")
    counts = _task_counts(directory)
    summary = f"  Passed: [green]{counts['passed']}[/green]   Failed: [red]{counts['failed'] + counts['timed_out']}[/red]" if counts["passed"] or counts["failed"] or counts["timed_out"] else ""
    lines = [
        f"[bold]Run:[/bold] {run.get('run_id')}",
        f"[bold]Status:[/bold] {_status(directory)}",
        f"[bold]Benchmark:[/bold] {run.get('benchmark')} {run.get('benchmark_version', '')}".strip(),
        f"[bold]Provider:[/bold] {run.get('provider')}",
        f"[bold]Model:[/bold] {run.get('benchmark_model')} (api {run.get('api_model')})",
        f"[bold]Tasks:[/bold] {run.get('task_count')}",
        f"[bold]Concurrency:[/bold] {run.get('concurrency')}  [bold]Trials:[/bold] {run.get('trials')}",
        f"[bold]Created:[/bold] {run.get('created_at_utc')}",
        f"[bold]Duration:[/bold] {_fmt_duration(_duration_seconds(directory))}",
        f"[bold]Directory:[/bold] {directory}",
    ]
    if summary:
        lines.append(summary)
    console.print(Panel("\n".join(lines), title="Run", expand=False))
    fingerprint = run.get("environment_fingerprint")
    if fingerprint:
        console.print(f"Environment fingerprint: [cyan]{fingerprint}[/cyan]")


@app.command()
def latest(
    provider: str | None = typer.Option(None, "--provider", help="Latest run for this provider"),
) -> None:
    """Show the most recent run's id."""
    directories = _all_run_dirs()
    if provider:
        directories = [d for d in directories if str((_run_json(d) or {}).get("provider", "")) == provider]
    if not directories:
        raise typer.BadParameter("no runs match")
    run = _run_json(directories[0]) or {}
    console.print(f"{run.get('run_id', directories[0].name)}")
