"""Structured run-progress events and per-task harbor result parsing.

Progress is emitted as :class:`ProgressEvent` objects through a callback so
the CLI, a future TUI, and a dashboard all consume identical structured
data instead of parsing strings. Task lifecycle events
(``task_started`` / ``task_completed`` / ``task_failed`` / ``task_timed_out``)
carry per-task fields.

Harbor writes one ``result.json`` per finished task under the run's
``harbor/`` jobs directory (mirroring analytics/analyze.py and the older
dashboard extractor); :func:`scan_harbor_results` reads them for live
progress during a run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LIFECYCLE_PHASES = frozenset({"docker", "tokenizer", "validate", "proxy", "running", "analyze", "done"})
TASK_LIFECYCLE = frozenset({"task_started", "task_completed", "task_failed", "task_timed_out"})


@dataclass(frozen=True)
class ProgressEvent:
    """Structured progress update emitted by benchmark.runner.run_one.

    Phase is one of LIFECYCLE_PHASES for harness lifecycle steps, or one of
    TASK_LIFECYCLE for per-task transitions. Task/summary fields are only
    populated for the relevant phases.
    """

    phase: str
    message: str = ""
    completed: int = 0
    total: int = 0
    passed: int = 0
    failed: int = 0
    running: int = 0
    elapsed_seconds: float = 0.0
    task_id: str | None = None
    ttft_ms: float | None = None
    decode_tps: float | None = None
    run_dir: str | None = None


ProgressFn = Any  # Callable[[ProgressEvent], None] — kept Any to avoid import cycles


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_result(path: Path) -> dict[str, Any] | None:
    """Parse a Harbor result.json into a normalized task outcome."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    task_name = str(data.get("task_name") or data.get("task_id") or "").replace("terminal-bench/", "")
    if not task_name:
        return None
    reward = None
    verifier = data.get("verifier_result") if isinstance(data.get("verifier_result"), dict) else {}
    if isinstance(verifier.get("rewards"), dict):
        reward = verifier["rewards"].get("reward")
    try:
        reward = float(reward) if reward is not None else None
    except (TypeError, ValueError):
        reward = None
    exc_info = data.get("exception_info") if isinstance(data.get("exception_info"), dict) else {}
    exception_type = exc_info.get("exception_type")
    timeout = bool(exception_type and ("timeout" in str(exception_type).lower()))
    outcome = "passed" if reward == 1.0 else "timed_out" if timeout else "failed"
    trial_id = data.get("trial_id") or data.get("trial_name") or data.get("trial")
    return {
        "task_name": task_name,
        "task_id": task_name,
        "trial_id": str(trial_id) if trial_id is not None else None,
        "reward": reward,
        "passed": reward == 1.0 if reward is not None else None,
        "outcome": outcome,
        "exception_type": exception_type,
        "duration_sec": data.get("duration_sec"),
        "timeout": timeout if exception_type else False if reward is not None else None,
    }

def scan_harbor_result_list(jobs_dir: Path) -> list[dict[str, Any]]:
    """Return every parseable Harbor task result without collapsing trials."""
    if not jobs_dir.is_dir():
        return []
    results = []
    for path in sorted(jobs_dir.rglob("result.json")):
        parsed = _parse_result(path)
        if parsed is not None:
            results.append(parsed)
    return results


def scan_harbor_results(jobs_dir: Path) -> dict[str, dict[str, Any]]:
    """Return the latest parsed result for each task name."""
    return {result["task_name"]: result for result in scan_harbor_result_list(jobs_dir)}
