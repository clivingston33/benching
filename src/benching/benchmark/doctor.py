"""Environment checks shared by CLI and interactive shell."""
from __future__ import annotations

import platform
import subprocess
import sys

from benching.benchmark._paths import resolve_executable
from benching.benchmark.benchmarks import active_root_config
from benching.benchmark.config import benchmark_spec
from benching.benchmark.tokenizer import tokenizer_metadata


def tool_version(name: str) -> str | None:
    path = resolve_executable(name)
    if path is None:
        return None
    try:
        completed = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return (completed.stdout or completed.stderr).strip()[:256] or None


def docker_daemon_running() -> bool:
    path = resolve_executable("docker")
    if path is None:
        return False
    try:
        completed = subprocess.run([str(path), "info"], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def checks() -> list[dict[str, object]]:
    from benching.benchmark.lifecycle import is_supported_execution_platform

    result: list[dict[str, object]] = [
        {"name": "Python", "ok": sys.version_info >= (3, 12), "detail": platform.python_version()},
        {
            "name": "Execution OS",
            "ok": is_supported_execution_platform(),
            "detail": platform.system() + (" (runs supported)" if is_supported_execution_platform() else " (runs require Linux/WSL; analysis only)"),
        },
    ]
    docker = resolve_executable("docker")
    daemon = docker_daemon_running()
    harbor = tool_version("harbor")
    omp = tool_version("omp")
    result.extend(
        [
            {"name": "Docker", "ok": docker is not None, "detail": docker or "not found"},
            {"name": "Docker daemon", "ok": daemon, "detail": "running" if daemon else "not running"},
            {"name": "Harbor", "ok": harbor is not None, "detail": harbor or "not found"},
            {"name": "OMP", "ok": omp is not None, "detail": omp or "not found"},
        ]
    )
    spec = None
    tasks_count = None
    try:
        spec = benchmark_spec(active_root_config())
    except SystemExit:
        spec = None
    if spec is not None and spec.tasks_dir.is_dir():
        tasks_count = sum(1 for path in spec.tasks_dir.iterdir() if path.is_dir())
    result.extend(
        [
            {"name": "Configuration", "ok": spec is not None, "detail": "valid" if spec is not None else "invalid"},
            {"name": "Tasks", "ok": spec is not None and tasks_count is not None, "detail": f"{tasks_count} found" if tasks_count is not None else "not found"},
        ]
    )
    tokenizer = tokenizer_metadata(spec) if spec is not None else None
    result.append({"name": "Tokenizer", "ok": tokenizer is not None and tokenizer["source"] == "huggingface", "detail": "cached" if tokenizer and tokenizer["source"] == "huggingface" else "not cached"})
    return result


def ready() -> bool:
    return all(bool(item["ok"]) for item in checks())

