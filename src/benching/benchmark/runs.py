"""Read-only run inspection shared by CLI and interactive shell."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from benching.benchmark._paths import runs_root
from benching.benchmark.status import scan_harbor_results


def all_run_dirs() -> list[Path]:
    """Run directories under the explicit runs root (override or ./runs)."""
    root = runs_root()
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / "run.json").is_file()),
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


#: Lifecycle states where the run is expected to still be progressing.
ACTIVE_STATUSES = ("running", "analyzing")


def _pid_alive(pid: int) -> bool:
    """Best-effort same-host liveness check for a recorded owner PID."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Includes Windows WinError 87 for PIDs with no such process.
        return False
    return True


def owner_pid(directory: Path) -> int | None:
    """Owner process recorded for a run, from status.json then the pid file."""
    try:
        value = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        if isinstance(value, dict) and value.get("pid") is not None:
            return int(value["pid"])
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    try:
        return int((directory / "pid").read_text(encoding="utf-8").strip().split()[0])
    except (OSError, IndexError, TypeError, ValueError):
        return None


def describe_run(directory: Path) -> dict[str, Any]:
    """Status plus a conservative stale/abandoned diagnostic.

    A run whose status says ``running``/``analyzing`` but whose recorded
    owner process is absent (or was never recorded) is reported stale.
    This is a read-only diagnostic: nothing is rewritten, so PID reuse or
    a foreign machine can only tilt toward "active", never toward
    destroying evidence. ``unknown``/terminal states are never stale.
    """
    current = status(directory)
    if current not in ACTIVE_STATUSES:
        return {"status": current, "stale": False, "detail": "", "pid": owner_pid(directory)}
    pid = owner_pid(directory)
    if pid is None:
        return {
            "status": current,
            "stale": True,
            "detail": f"stale: status is {current!r} but no owner process was recorded on this host",
            "pid": None,
        }
    if _pid_alive(pid):
        return {"status": current, "stale": False, "detail": "", "pid": pid}
    return {
        "status": current,
        "stale": True,
        "detail": f"stale: status is {current!r} but owner process {pid} is not active on this host",
        "pid": pid,
    }


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

