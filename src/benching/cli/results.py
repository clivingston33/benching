"""benching results — read benchmark results for a run.

Thin presentation over :mod:`benching.benchmark.results`: viewing is
read-only (the canonical ``summary.json`` is shown as-is, never
recomputed); only ``reanalyze`` regenerates artifacts, explicitly.
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from benching.benchmark.results import load_result, reanalyze_run, summary_for
from benching.benchmark.runs import describe_run, duration_seconds, format_duration, run_json, status, task_counts

app = typer.Typer(help="Read run results.", no_args_is_help=True)
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


def _load(run_id: str, provider: str | None):
    """Core result loading, translated into a CLI usage error."""
    try:
        return load_result(run_id, provider=provider)
    except SystemExit as exc:
        raise typer.BadParameter(str(exc.code or exc)) from None


@app.command()
def show(
    run_id: str,
    provider: str | None = typer.Option(None, "--provider", help="Show the latest run for this provider (ignored when run_id is explicit)"),
) -> None:
    """Show normalized metrics + summary for a run (id, prefix, or 'latest').

    Read-only: shows the canonical summary without renormalizing. Use
    `benching results reanalyze` to explicitly regenerate it.
    """
    directory, summary = _load(run_id, provider)
    _render_metrics(directory, summary)


@app.command()
def latest(
    provider: str | None = typer.Option(None, "--provider", help="Latest run for this provider"),
) -> None:
    """Show results for the most recent run."""
    show("latest", provider=provider)


@app.command()
def reanalyze(run_id: str) -> None:
    """Explicitly regenerate one run's metrics/summary from its evidence."""
    from benching.benchmark.runs import resolve_run

    try:
        directory = resolve_run(run_id)
    except SystemExit as exc:
        raise typer.BadParameter(str(exc.code or exc)) from None
    summary = reanalyze_run(directory)
    if summary is None:
        raise typer.BadParameter(f"no normalizable telemetry in {directory}")
    console.print(f"[green]Reanalyzed:[/green] [cyan]{directory.name}[/cyan]")


def _render_metrics(directory, summary: dict | None) -> None:
    run = run_json(directory) or {}
    benchmark = f"{run.get('benchmark', '?')} {run.get('benchmark_version', '')}".strip()
    title = f"{benchmark} — {run.get('provider', '?')}"
    console.rule(title)
    console.print(f"Run: [bold]{directory.name}[/bold]  Status: {_display_status(directory)}")
    model = run.get("benchmark_model")
    api_model = run.get("api_model")
    console.print(f"Model: {model} (api {api_model})" if model and api_model else f"Model: {model or api_model or '?'}")
    counts = task_counts(directory)
    if counts["passed"] or counts["failed"] or counts["timed_out"]:
        console.print(
            f"Tasks: [green]{counts['passed']} passed[/green] / [red]{counts['failed']} failed[/red] / [yellow]{counts['timed_out']} timed out[/yellow]  ({format_duration(duration_seconds(directory))})"
        )

    if summary is None:
        console.print("[yellow]No normalized metrics yet; run `benching results reanalyze RUN` to regenerate them.[/yellow]")
        return
    _render_timing(summary)
    _render_reliability(summary)
    _render_tasks(summary)
    _render_tokens(summary)


def _render_timing(summary: dict) -> None:
    timing = Table(title="Latency / throughput", show_header=True, header_style="bold")
    timing.add_column("Metric")
    timing.add_column("Mean")
    timing.add_column("Median")
    timing.add_column("p95")
    timing.add_column("Count")
    metric_rows = (
        ("TTFT (ms)", "ttft_ms"),
        ("Decode duration (ms)", "decode_duration_ms"),
        ("End-to-end (ms)", "end_to_end_latency_ms"),
        ("Decode TPS", "decode_tps"),
        ("Effective TPS", "effective_tps"),
    )
    for label, key in metric_rows:
        dist = (summary.get("timing") or {}).get(key) or {}
        timing.add_row(
            label,
            _fmt(dist.get("mean")),
            _fmt(dist.get("median")),
            _fmt(dist.get("p95")),
            str(dist.get("count", "—")),
        )
    console.print(timing)


def _render_reliability(summary: dict) -> None:
    reliability = summary.get("reliability") or {}
    requests = summary.get("requests")
    table = Table(title="Reliability", show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value")
    rows = [("requests", "Requests")] if requests is not None else []
    rows.extend(
        (
            ("request_success_rate", "Request success rate"),
            ("stream_completion_rate", "Stream completion rate"),
            ("http_error_rate", "HTTP error rate"),
            ("timeout_rate", "Timeout rate"),
            ("provider_failures", "Provider failures"),
            ("downstream_cancellations", "Downstream cancellations"),
        )
    )
    for key, label in rows:
        value = requests if key == "requests" else reliability.get(key)
        table.add_row(label, _fmt(value))
    console.print(table)


def _render_tasks(summary: dict) -> None:
    benchmark_stats = summary.get("benchmark") or {}
    if not benchmark_stats.get("total_tasks"):
        return
    tasks = Table(title="Task results", show_header=True, header_style="bold")
    tasks.add_column("Total")
    tasks.add_column("Completed")
    tasks.add_column("Passed")
    tasks.add_column("Failed")
    tasks.add_column("Errored")
    tasks.add_row(
        str(benchmark_stats.get("total_tasks", "—")),
        str(benchmark_stats.get("completed_tasks", "—")),
        str(benchmark_stats.get("passed_tasks", "—")),
        str(benchmark_stats.get("failed_tasks", "—")),
        str(benchmark_stats.get("errored_tasks", "—")),
    )
    console.print(tasks)


def _render_tokens(summary: dict) -> None:
    tokens = summary.get("tokens") or {}
    if not any(tokens.get(key) for key in ("input_provider", "output_provider", "output_local")):
        return
    console.print(
        f"Tokens: input {tokens.get('input_provider') or 0}"
        f" / output provider {tokens.get('output_provider') or 0}"
        f" / output local {tokens.get('output_local') or 0}"
    )


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
