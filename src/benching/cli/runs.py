"""benching runs — inspect benchmark run directories.

Thin presentation over :mod:`benching.benchmark.runs`: this module renders
tables/details only. Run discovery, status, stale diagnostics, durations,
and task counts all live in the core API so Typer and the slash shell
represent the same runs identically.
"""
from __future__ import annotations

from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from benching.benchmark.runs import (
    all_run_dirs,
    describe_run,
    duration_seconds,
    format_duration,
    resolve_run,
    run_json,
    status,
    task_counts,
)

app = typer.Typer(help="Inspect past benchmark runs.", no_args_is_help=False)
console = Console()


def _display_status(directory) -> str:
    """Status text with a stale-run diagnostic marker when applicable."""
    try:
        described = describe_run(directory)
    except Exception:
        return status(directory)
    if described.get("stale"):
        return f"{described['status']} (stale)"
    return str(described.get("status", "unknown"))


def _resolve_run(run_ref: str):
    """Core run resolution, translated into a CLI usage error."""
    try:
        return resolve_run(run_ref)
    except SystemExit as exc:
        raise typer.BadParameter(str(exc.code or exc)) from None


def _format_age(path) -> str:
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


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    """Bare `benching runs` lists runs (M5: documented invocation works)."""
    if ctx.invoked_subcommand is None:
        render_runs()


def render_runs(provider: str | None = None, status: str | None = None) -> None:
    """Render the runs table; plain defaults so the bare-command callback can call it directly."""
    directories = all_run_dirs()
    if provider:
        directories = [d for d in directories if str((run_json(d) or {}).get("provider", "")) == provider]
    if status:
        directories = [d for d in directories if _display_status(d) == status]
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
        run = run_json(directory)
        name = directory.name
        provider_name = str((run or {}).get("provider", "?"))
        mode = "smoke" if "-smoke-" in name else ("full" if "-full-" in name else "?")
        benchmark = f"{run.get('benchmark', '?')} {run.get('benchmark_version', '')}".strip() if run else "?"
        counts = task_counts(directory)
        passed_col = str(counts["passed"]) if counts["passed"] or counts["failed"] or counts["timed_out"] else "—"
        failed_col = str(counts["failed"] + counts["timed_out"]) if counts["passed"] or counts["failed"] or counts["timed_out"] else "—"
        table.add_row(
            name,
            provider_name,
            mode,
            benchmark,
            _display_status(directory),
            passed_col,
            failed_col,
            format_duration(duration_seconds(directory)),
            _format_age(directory),
        )
    console.print(table)


@app.command("list")
def list(
    provider: str | None = typer.Option(None, "--provider", help="Filter by provider name"),
    status: str | None = typer.Option(None, "--status", help="Filter by run status (e.g. completed, failed, running)"),
) -> None:
    """List benchmark runs, newest first, with optional filters."""
    render_runs(provider, status)


@app.command("show")
def show(run_id: str) -> None:
    """Show full configuration of one run (by id, id prefix, or 'latest')."""
    directory = _resolve_run(run_id)
    run = run_json(directory)
    if run is None:
        raise typer.BadParameter(f"run.json unreadable in {directory}")
    counts = task_counts(directory)
    summary = f"  Passed: [green]{counts['passed']}[/green]   Failed: [red]{counts['failed'] + counts['timed_out']}[/red]" if counts["passed"] or counts["failed"] or counts["timed_out"] else ""
    lines = [
        f"[bold]Run:[/bold] {run.get('run_id')}",
        f"[bold]Status:[/bold] {_display_status(directory)}",
        f"[bold]Benchmark:[/bold] {run.get('benchmark')} {run.get('benchmark_version', '')}".strip(),
        f"[bold]Provider:[/bold] {run.get('provider')}",
        f"[bold]Model:[/bold] {run.get('benchmark_model')} (api {run.get('api_model')})",
        f"[bold]Tasks:[/bold] {run.get('task_count')}",
        f"[bold]Concurrency:[/bold] {run.get('concurrency')}  [bold]Trials:[/bold] {run.get('trials')}",
        f"[bold]Created:[/bold] {run.get('created_at_utc')}",
        f"[bold]Duration:[/bold] {format_duration(duration_seconds(directory))}",
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
    directories = all_run_dirs()
    if provider:
        directories = [d for d in directories if str((run_json(d) or {}).get("provider", "")) == provider]
    if not directories:
        raise typer.BadParameter("no runs match")
    run = run_json(directories[0]) or {}
    console.print(f"{run.get('run_id', directories[0].name)}")
