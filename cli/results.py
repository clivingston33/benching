"""benching results — read benchmark results for a run."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from analytics.analyze import normalize_runs
from cli.runs import _resolve_run, _run_json, _status

app = typer.Typer(help="Read run results.", no_args_is_help=True)
console = Console()


@app.command()
def show(
    run_id: str,
    provider: str | None = typer.Option(None, "--provider", help="Show the latest run for this provider (ignored when run_id is explicit)"),
) -> None:
    """Show normalized metrics + summary for a run (id, prefix, or 'latest')."""
    if run_id == "latest" and provider:
        from cli.runs import _all_run_dirs

        matches = [d for d in _all_run_dirs() if str((_run_json(d) or {}).get("provider", "")) == provider]
        if not matches:
            raise typer.BadParameter(f"no runs for provider {provider!r}")
        directory = matches[0]
    else:
        directory = _resolve_run(run_id)
    if not (directory / "raw.jsonl").is_file() and not (directory / "metrics.jsonl").is_file():
        raise typer.BadParameter(f"no telemetry found in {directory}")
    if not (directory / "metrics.jsonl").is_file() or _stale(directory):
        console.print("[yellow]Normalizing telemetry...[/yellow]")
        normalize_runs([directory], execution="sequential", write_comparison=False)
    _render_metrics(directory, _summary_for(directory))


@app.command()
def latest(
    provider: str | None = typer.Option(None, "--provider", help="Latest run for this provider"),
) -> None:
    """Show results for the most recent run."""
    show("latest", provider=provider)


def _stale(directory: Path) -> bool:
    """metrics.jsonl is stale when raw.jsonl is newer (run still streaming or re-run)."""
    raw = directory / "raw.jsonl"
    metrics = directory / "metrics.jsonl"
    if not raw.is_file() or not metrics.is_file():
        return False
    try:
        return raw.stat().st_mtime > metrics.stat().st_mtime
    except OSError:
        return False


def _render_metrics(directory: Path, summary: dict | None) -> None:
    from cli.runs import _duration_seconds, _fmt_duration, _task_counts

    run = _run_json(directory) or {}
    benchmark = f"{run.get('benchmark', '?')} {run.get('benchmark_version', '')}".strip()
    title = f"{benchmark} — {run.get('provider', '?')}"
    console.rule(title)
    console.print(f"Run: [bold]{directory.name}[/bold]  Status: {_status(directory)}")
    model = run.get("benchmark_model")
    api_model = run.get("api_model")
    console.print(f"Model: {model} (api {api_model})" if model and api_model else f"Model: {model or api_model or '?'}")
    counts = _task_counts(directory)
    if counts["passed"] or counts["failed"] or counts["timed_out"]:
        console.print(
            f"Tasks: [green]{counts['passed']} passed[/green] / [red]{counts['failed']} failed[/red] / [yellow]{counts['timed_out']} timed out[/yellow]  ({_fmt_duration(_duration_seconds(directory))})"
        )

    if summary is None:
        console.print("[yellow]No normalized metrics yet.[/yellow]")
        return
    _render_timing(summary)
    _render_reliability(summary)
    _render_tasks(summary)
    _render_tokens(summary)


def _summary_for(directory: Path) -> dict | None:
    """Reconstruct the run's summary from metrics.jsonl via analyze.summerize."""
    from analytics import analyze as A

    run = _run_json(directory) or {}
    rows = []
    metrics_path = directory / "metrics.jsonl"
    if metrics_path.is_file():
        for line in metrics_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except json.JSONDecodeError:
                continue
    if not rows:
        return None
    try:
        return A.summarize(run, rows, directory)
    except Exception:
        return None


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
    for key, label in (
        ("request_success_rate", "Request success rate"),
        ("stream_completion_rate", "Stream completion rate"),
        ("http_error_rate", "HTTP error rate"),
        ("timeout_rate", "Timeout rate"),
        ("provider_failures", "Provider failures"),
        ("downstream_cancellations", "Downstream cancellations"),
    ):
        rows.append((key, label))
    for key, label in rows:
        value = requests if key == "requests" else reliability.get(key)
        table.add_row(label, _fmt(value))
    console.print(table)


def _render_tasks(summary: dict) -> None:
    benchmark_stats = summary.get("benchmark") or {}
    if not benchmark_stats or not benchmark_stats.get("total_tasks"):
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
        f"Tokens: input {tokens.get('input_provider') or 0} / output provider {tokens.get('output_provider') or 0} / output local {tokens.get('output_local') or 0}"
    )


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
