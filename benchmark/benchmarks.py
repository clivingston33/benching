"""Benchmark registry: named local suites as manifests the runner consumes.

Each benchmark is a YAML manifest under ``~/.config/benching/benchmarks/``
holding the same fields ``BenchmarkSpec`` already reads from the repo's
config/benchmark.yaml — so ``benchmark.config.benchmark_spec`` consumes it
unchanged.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from benchmark.config import load_yaml
from benchmark.state import benchmarks_dir, update_state

REQUIRED_FIELDS = ("name", "version", "tasks_dir", "agent")


def manifest_path(name: str) -> Path:
    return benchmarks_dir() / f"{name}.yaml"


def list_benchmarks() -> list[dict[str, Any]]:
    """All registered benchmarks: name, display name, task count, active flag."""
    import yaml

    from benchmark.state import load_state

    active = load_state().active_benchmark
    entries: list[dict[str, Any]] = []
    directory = benchmarks_dir()
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        settings = data.get("benchmark") if isinstance(data, dict) else None
        if not isinstance(settings, dict):
            continue
        entries.append(
            {
                "name": path.stem,
                "display": f"{settings.get('name', path.stem)} {settings.get('version', '')}".strip(),
                "expected_task_count": settings.get("expected_task_count"),
                "tasks_dir": settings.get("tasks_dir"),
                "active": path.stem == active,
            }
        )
    return entries


def load_manifest(name: str) -> dict[str, Any]:
    """Load one benchmark manifest as a root config dict (benchmark: key)."""
    path = manifest_path(name)
    if not path.is_file():
        raise SystemExit(f"unknown benchmark: {name}")
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("benchmark"), dict):
        raise SystemExit(f"invalid benchmark manifest: {path}")
    return data


def add_benchmark(name: str, settings: dict[str, Any], make_active: bool = True) -> Path:
    """Write a benchmark manifest; validates required fields and tasks dir."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise SystemExit("benchmark name must contain only letters, numbers, '-' or '_'")
    missing = [field for field in REQUIRED_FIELDS if not str(settings.get(field, "") or "").strip()]
    if missing:
        raise SystemExit(f"benchmark manifest missing field(s): {', '.join(missing)}")
    tasks_dir = Path(str(settings["tasks_dir"])).expanduser()
    if not tasks_dir.is_dir():
        raise SystemExit(f"tasks directory not found: {tasks_dir}")
    if manifest_path(name).is_file():
        raise SystemExit(f"benchmark already exists: {name}")

    import yaml
    path = manifest_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"benchmark": settings}
    path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    if make_active:
        update_state(active_benchmark=name)
    return path


def remove_benchmark(name: str) -> None:
    path = manifest_path(name)
    if not path.is_file():
        raise SystemExit(f"unknown benchmark: {name}")
    path.unlink()
    from benchmark.state import load_state, save_state

    state = load_state()
    if state.active_benchmark == name:
        state.active_benchmark = None
        save_state(state)


def set_active_benchmark(name: str) -> dict[str, Any]:
    """Make ``name`` the active benchmark and return its manifest."""
    manifest = load_manifest(name)
    update_state(active_benchmark=name)
    return manifest


def active_root_config() -> dict[str, Any]:
    """Merged root config for the active benchmark, or the repo default.

    The user's active benchmark manifest overlays the repo's
    config/benchmark.yaml (which contributes provider entries); the repo
    benchmark stays the fallback when no user benchmark is active.
    """
    from benchmark.state import load_state

    name = load_state().active_benchmark
    root = load_yaml()
    if name:
        manifest = load_manifest(name)
        root = dict(root)
        root["benchmark"] = manifest["benchmark"]
    return root
