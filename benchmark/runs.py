"""Read-only run inspection shared by CLI and interactive shell."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmark._paths import RUNS
from benchmark.status import scan_harbor_results


def all_run_dirs() -> list[Path]:
    if not RUNS.is_dir():
        return []
    return sorted(
        (path for path in RUNS.iterdir() if path.is_dir() and (path / "run.json").is_file()),
        key=lambda path: path.name,
        reverse=True,
    )


def run_json(directory: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def status(directory: Path) -> str:
    try:
        value = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    return str(value.get("status", "unknown")) if isinstance(value, dict) else "unknown"


def resolve_run(run_ref: str) -> Path:
    directories = all_run_dirs()
    if not directories:
        raise SystemExit("no runs found under runs/")
    if run_ref == "latest":
        return directories[0]
    matches = [directory for directory in directories if directory.name.startswith(run_ref)]
    if not matches:
        raise SystemExit(f"no run matches {run_ref!r}; see `benching runs`")
    if len(matches) > 1:
        raise SystemExit(f"run reference {run_ref!r} is ambiguous")
    return matches[0]


def duration_seconds(directory: Path) -> float | None:
    run = run_json(directory) or {}
    try:
        status_data = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        created = datetime.fromisoformat(str(run["created_at_utc"]).replace("Z", "+00:00"))
        updated = datetime.fromisoformat(str(status_data["updated_at_utc"]).replace("Z", "+00:00"))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return max(0.0, (updated - created).total_seconds())


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def task_counts(directory: Path) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "timed_out": 0}
    for result in scan_harbor_results(directory / "harbor").values():
        outcome = result.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
    return counts
