"""benching results — read benchmark results for a run."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from benchmark._paths import ROOT

from cli.runs import _resolve_run, _run_json, _status

app = typer.Typer(help="Read run results.", no_args_is_help=True)
console = Console()


@app.command()
def show(run_id: str) -> None:
    """Show normalized metrics + summary for a run (id, prefix, or 'latest')."""
    directory = _resolve_run(run_id)
    if (directory / "metrics.jsonl").is_file():
        _render_metrics(directory)
    else:
        console.print("[yellow]No metrics yet; normalizing raw telemetry...[/yellow]")
        _analyze(directory)
        if (directory / "metrics.jsonl").is_file():
            _render_metrics(directory)
        else:
            console.print("[red]No raw telemetry found for this run.[/red]")
            raise typer.Exit(1)


@app.command()
def latest() -> None:
    """Show results for the most recent run."""
    show("latest")


def _analyze(directory: Path) -> None:
    subprocess.run([sys.executable, str(ROOT / "analytics" / "analyze.py"), str(directory)], cwd=ROOT, check=True)


def _render_metrics(directory: Path) -> None:
    run = _run_json(directory) or {}
    metrics = _read_metrics(directory)
    benchmark = f"{run.get('benchmark', '?')} {run.get('benchmark_version', '')}".strip()
    title = f"{benchmark} — {run.get('provider', '?')}"
    console.rule(title)
    console.print(f"Run: [bold]{directory.name}[/bold]  Status: {_status(directory)}")
    model = run.get("benchmark_model")
    api_model = run.get("api_model")
    console.print(f"Model: {model} (api {api_model})" if model and api_model else f"Model: {model or api_model or '?'}")

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
        dist = (metrics.get("timing") or {}).get(key) or {}
        timing.add_row(
            label,
            _fmt(dist.get("mean")),
            _fmt(dist.get("median")),
            _fmt(dist.get("p95")),
            str(dist.get("count", "—")),
        )
    console.print(timing)

    reliability = metrics.get("reliability") or {}
    summary = Table(title="Reliability", show_header=True, header_style="bold")
    summary.add_column("Metric")
    summary.add_column("Value")
    for key, label in (
        ("requests", "Requests"),
        ("request_success_rate", "Request success rate"),
        ("stream_completion_rate", "Stream completion rate"),
        ("http_error_rate", "HTTP error rate"),
        ("timeout_rate", "Timeout rate"),
        ("provider_failures", "Provider failures"),
        ("downstream_cancellations", "Downstream cancellations"),
    ):
        summary.add_row(label, _fmt(reliability.get(key)))
    console.print(summary)

    benchmark_stats = metrics.get("benchmark") or {}
    if benchmark_stats:
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
    if metrics.get("tokens") and any(metrics["tokens"].get(k) for k in ("input_provider", "output_provider", "output_local")):
        tokens = metrics["tokens"]
        console.print(f"Tokens: input {tokens.get('input_provider') or 0} / output provider {tokens.get('output_provider') or 0} / output local {tokens.get('output_local') or 0}")


def _read_metrics(directory: Path) -> dict:
    rows = []
    for line in (directory / "metrics.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except json.JSONDecodeError:
            continue
    # Build a summary-equivalent view from normalized rows.
    return _summarize_rows(rows)


def _summarize_rows(rows: list[dict]) -> dict:
    """Aggregate normalized metric rows into a summary dict (mirrors summarize())."""
    import math
    import statistics

    def dist(values: list[float]) -> dict:
        if not values:
            return {"count": 0, "mean": None, "median": None, "p95": None}
        return {
            "count": len(values),
            "mean": round(statistics.fmean(values), 6),
            "median": round(statistics.median(values), 6),
            "p95": _p95(values),
        }

    def collect(section: str, key: str) -> list[float]:
        out = []
        for row in rows:
            value = ((row.get(section) or {}).get(key) or {}).get("value")
            if isinstance(value, (int, float)):
                out.append(float(value))
        return out

    success = sum(1 for row in rows if (row.get("reliability") or {}).get("success"))
    streams = sum(1 for row in rows if (row.get("reliability") or {}).get("stream_completed"))
    n = len(rows)
    http_errors = sum(1 for row in rows if isinstance(((row.get("reliability") or {}).get("http_status")), int) and row["reliability"]["http_status"] >= 400)
    timeouts = sum(1 for row in rows if (row.get("reliability") or {}).get("timeout"))
    provider_failures = sum(1 for row in rows if (row.get("reliability") or {}).get("provider_stream_failure"))
    cancelled = sum(1 for row in rows if (row.get("reliability") or {}).get("downstream_cancelled"))
    return {
        "requests": n,
        "reliability": {
            "requests": n,
            "request_success_rate": success / n if n else None,
            "stream_completion_rate": streams / n if n else None,
            "http_error_rate": http_errors / n if n else None,
            "timeout_rate": timeouts / n if n else None,
            "provider_failures": provider_failures,
            "downstream_cancellations": cancelled,
        },
        "timing": {key: dist(collect("timing", key)) for key in ("ttft_ms", "decode_duration_ms", "end_to_end_latency_ms", "decode_tps", "effective_tps")},
        "tokens": {
            "input_provider": sum(collect("tokens", "input_provider")) or None,
            "output_provider": sum(collect("tokens", "output_provider")) or None,
            "output_local": sum(collect("tokens", "output_local")) or None,
        },
        "benchmark": {},
    }


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * 0.95
    import math

    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return round(ordered[low], 6)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 6)


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
