"""Benchmark registry: named local suites as manifests the runner consumes.

Each benchmark is a YAML manifest under ``~/.config/benching/benchmarks/``
holding the same fields ``BenchmarkSpec`` already reads from the packaged
default manifest — so ``benching.benchmark.config.benchmark_spec`` consumes it
unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from benching.benchmark.config import load_yaml
from benching.benchmark.security import ensure_within_directory, validate_registry_name
from benching.benchmark.state import benchmarks_dir, update_state

REQUIRED_FIELDS = ("name", "version", "tasks_dir", "agent")


def manifest_path(name: str) -> Path:
    """Registry manifest path with name validation and containment.

    Rejects ``../``, absolute paths, and separators via the shared
    registry-name rule and requires the resolved path to stay inside
    the application benchmarks directory.
    """
    validate_registry_name(name, "benchmark")
    candidate = benchmarks_dir() / f"{name}.yaml"
    ensure_within_directory(benchmarks_dir(), candidate)
    return candidate


def list_benchmarks() -> list[dict[str, Any]]:
    """All registered benchmarks: name, display name, task count, active flag."""
    import yaml

    from benching.benchmark.state import load_state

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
    """Load one benchmark manifest as a root config dict (benchmark: key).

    A malformed file is reported with its path, never silently replaced.
    """
    path = manifest_path(name)
    if not path.is_file():
        raise SystemExit(f"unknown benchmark: {name}")
    import yaml

    from benching.benchmark.io import yaml_error_summary

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SystemExit(f"invalid benchmark manifest: {path} ({yaml_error_summary(exc)})") from None
    if not isinstance(data, dict) or not isinstance(data.get("benchmark"), dict):
        raise SystemExit(f"invalid benchmark manifest: {path}")
    return data


def add_benchmark(name: str, settings: dict[str, Any], make_active: bool = True) -> Path:
    """Write a benchmark manifest; validates required fields and tasks dir."""
    validate_registry_name(name, "benchmark")
    missing = [field for field in REQUIRED_FIELDS if not str(settings.get(field, "") or "").strip()]
    if missing:
        raise SystemExit(f"benchmark manifest missing field(s): {', '.join(missing)}")
    tasks_dir = Path(str(settings["tasks_dir"])).expanduser()
    if not tasks_dir.is_dir():
        raise SystemExit(f"tasks directory not found: {tasks_dir}")
    if manifest_path(name).is_file():
        raise SystemExit(f"benchmark already exists: {name}")

    from benching.benchmark.io import dump_yaml_atomic

    path = manifest_path(name)
    dump_yaml_atomic(path, {"benchmark": settings}, sort_keys=False)
    if make_active:
        update_state(active_benchmark=name)
    return path


def remove_benchmark(name: str) -> None:
    path = manifest_path(name)
    if not path.is_file():
        raise SystemExit(f"unknown benchmark: {name}")
    path.unlink()
    from benching.benchmark.state import load_state, save_state

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
    """Merged root config for the active benchmark, or the packaged default.

    The user's active benchmark manifest overlays the packaged default
    manifest; the default stays the fallback when no user benchmark is
    active.
    """
    from benching.benchmark.state import load_state

    name = load_state().active_benchmark
    root = load_yaml()
    if name:
        manifest = load_manifest(name)
        root = dict(root)
        root["benchmark"] = manifest["benchmark"]
    return root

