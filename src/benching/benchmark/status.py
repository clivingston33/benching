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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LIFECYCLE_PHASES = frozenset({"docker", "tokenizer", "validate", "proxy", "running", "analyze", "done"})
TASK_LIFECYCLE = frozenset({"task_started", "task_completed", "task_failed", "task_timed_out"})


@dataclass(frozen=True)
class ProgressEvent:
    """Structured progress update emitted by benching.benchmark.runner.run_one.

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


ProgressFn = Callable[[ProgressEvent], None]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


#: Harbor suite/task separator convention: Harbor result files name tasks
#: as "<suite>/<task>". Only this Harbor adapter knows that convention;
#: generic analytics must never strip suite-specific prefixes itself.
HARBOR_TASK_ID_PREFIX = "terminal-bench/"


def normalize_harbor_task_id(raw: Any) -> str:
    """Reduce a Harbor task identity to the generic benchmark task id.

    Strips one leading Harbor suite prefix. Arbitrary or embedded prefixes
    are left untouched: only the documented Harbor convention normalizes.
    """
    text = str(raw or "")
    if text.startswith(HARBOR_TASK_ID_PREFIX):
        return text[len(HARBOR_TASK_ID_PREFIX):]
    return text


def _parse_result(path: Path) -> dict[str, Any] | None:
    """Parse a Harbor result.json into a normalized task outcome.

    The numeric verifier reward is preserved exactly; ``passed`` is a
    derived binary convenience (``reward == 1.0``) for the current binary
    suite and must not replace ``reward``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    task_name = normalize_harbor_task_id(data.get("task_name") or data.get("task_id"))
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
    """Return every parseable Harbor task result without collapsing trials.

    Tolerant by design: live progress and listings must survive mid-run
    partial files. Analysis uses read_harbor_results_strict instead.
    """
    if not jobs_dir.is_dir():
        return []
    results = []
    for path in sorted(jobs_dir.rglob("result.json")):
        parsed = _parse_result(path)
        if parsed is not None:
            results.append(parsed)
    return results


def read_harbor_results_strict(jobs_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Parse every Harbor result file, failing closed on corrupt evidence.

    Returns [(path, parsed)] in sorted path order. Aggregate-shaped files
    (Harbor stats without task identity, consumed by benchmark_result) are
    skipped. Anything else unparseable raises SystemExit naming the file.
    Duplicate (task, trial) identities keep the first sorted path with a
    stderr diagnostic when payloads agree, and raise SystemExit when they
    conflict: analysis must never silently pick one.
    """
    import sys

    found: list[tuple[Path, dict[str, Any]]] = []
    if jobs_dir.is_dir():
        for path in sorted(jobs_dir.rglob("result.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SystemExit(f"malformed Harbor result: {path} ({type(exc).__name__})") from None
            if not isinstance(data, dict):
                raise SystemExit(f"malformed Harbor result: {path} (expected object)")
            if not data.get("task_name") and not data.get("task_id"):
                if "stats" in data or "n_total_trials" in data:
                    continue
                raise SystemExit(f"malformed Harbor result: {path} (missing task identity)")
            parsed = _parse_result(path)
            if parsed is None:
                raise SystemExit(f"malformed Harbor result: {path} (missing task identity)")
            found.append((path, parsed))
    unique: list[tuple[Path, dict[str, Any]]] = []
    seen: dict[tuple[str, str | None], tuple[Path, dict[str, Any]]] = {}
    for path, parsed in found:
        key = (parsed["task_id"], parsed["trial_id"])
        previous = seen.get(key)
        if previous is None:
            seen[key] = (path, parsed)
            unique.append((path, parsed))
        elif previous[1] == parsed:
            print(f"warning: duplicate Harbor result ignored: {path} (task={key[0]} trial={key[1]})", file=sys.stderr)
        else:
            raise SystemExit(
                f"duplicate Harbor result identity: task {key[0]} trial {key[1]} "
                f"({previous[0]} vs {path})"
            )
    return unique


def scan_harbor_results(jobs_dir: Path) -> dict[tuple[str, str | None], dict[str, Any]]:
    """Return the latest parsed result for each (task, trial) identity.

    Trials never collapse: two attempts of one task remain two entries.
    Callers that only need totals iterate over ``.values()`` unchanged.
    With duplicate files for one identity the latest sorted path wins
    deterministically here; analysis itself diagnoses duplicates loudly.
    """
    ordered: dict[tuple[str, str | None], dict[str, Any]] = {}
    for result in scan_harbor_result_list(jobs_dir):
        ordered[(result["task_name"], result["trial_id"])] = result
    return ordered
