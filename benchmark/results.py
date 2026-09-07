"""Result normalization and summary helpers shared by CLI surfaces."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analytics.analyze import normalize_runs, summarize
from benchmark.runs import resolve_run, run_json


def stale(directory: Path) -> bool:
    raw = directory / "raw.jsonl"
    metrics = directory / "metrics.jsonl"
    if not raw.is_file() or not metrics.is_file():
        return False
    try:
        return raw.stat().st_mtime > metrics.stat().st_mtime
    except OSError:
        return False


def summary_for(directory: Path) -> dict[str, Any] | None:
    metrics_path = directory / "metrics.jsonl"
    if not metrics_path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    for line in metrics_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    if not rows:
        return None
    run = run_json(directory) or {}
    try:
        return summarize(run, rows, directory)
    except Exception:
        return None


def ensure_normalized(run_ref: str = "latest", provider: str | None = None) -> tuple[Path, dict[str, Any] | None]:
    if run_ref == "latest" and provider:
        from benchmark.runs import all_run_dirs

        matches = [directory for directory in all_run_dirs() if str((run_json(directory) or {}).get("provider", "")) == provider]
        if not matches:
            raise SystemExit(f"no runs for provider {provider!r}")
        directory = matches[0]
    else:
        directory = resolve_run(run_ref)
    if not (directory / "raw.jsonl").is_file() and not (directory / "metrics.jsonl").is_file():
        raise SystemExit(f"no telemetry found in {directory}")
    if not (directory / "metrics.jsonl").is_file() or stale(directory):
        normalize_runs([directory], execution="sequential", write_comparison=False)
    return directory, summary_for(directory)
