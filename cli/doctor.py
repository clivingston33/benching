"""benching doctor — environment health checks."""
from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from benchmark._paths import CONFIG, RUNS
from benchmark.config import benchmark_spec, load_yaml
from benchmark.tokenizer import tokenizer_metadata

app = typer.Typer(help="Check the benching environment.", no_args_is_help=True)
console = Console()


def _tool_version(name: str) -> str | None:
    import subprocess

    path = shutil.which(name)
    if path is None:
        return None
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return (completed.stdout or completed.stderr).strip()[:256] or None


def _docker_daemon_running() -> bool:
    import subprocess

    path = shutil.which("docker")
    if path is None:
        return False
    try:
        completed = subprocess.run([path, "info"], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _checks() -> list[dict[str, object]]:
    """Collect (name, ok, detail) checks without rendering."""
    import platform
    import sys

    checks: list[dict[str, object]] = []
    checks.append({"name": "Python", "ok": sys.version_info >= (3, 12), "detail": platform.python_version()})
    docker = shutil.which("docker")
    checks.append({"name": "Docker", "ok": docker is not None, "detail": docker or "not found"})
    checks.append({"name": "Docker daemon", "ok": _docker_daemon_running(), "detail": "running" if _docker_daemon_running() else "not running"})
    checks.append({"name": "Harbor", "ok": _tool_version("harbor") is not None, "detail": _tool_version("harbor") or "not found"})
    checks.append({"name": "OMP", "ok": _tool_version("omp") is not None, "detail": _tool_version("omp") or "not found"})

    config_ok = CONFIG.is_file()
    spec = None
    tasks_count = None
    if config_ok:
        try:
            spec = benchmark_spec(load_yaml())
        except SystemExit:
            spec = None
        if spec is not None and spec.tasks_dir.is_dir():
            tasks_count = sum(1 for path in spec.tasks_dir.iterdir() if path.is_dir())
    checks.append({"name": "Configuration", "ok": spec is not None, "detail": "valid" if spec is not None else "invalid"})
    checks.append(
        {
            "name": "Tasks",
            "ok": spec is not None and tasks_count is not None,
            "detail": f"{tasks_count} found" if tasks_count is not None else (str(spec.tasks_dir) if spec is not None else "no config"),
        }
    )
    if spec is not None:
        tokenizer = tokenizer_metadata(spec)
        checks.append({"name": "Tokenizer", "ok": tokenizer["source"] == "huggingface", "detail": "cached" if tokenizer["source"] == "huggingface" else "not cached"})
    else:
        checks.append({"name": "Tokenizer", "ok": False, "detail": "no config"})
    return checks


@app.command()
def check() -> None:
    """Run environment checks and print a status table."""
    from rich.table import Table

    checks = _checks()
    table = Table(title="benching environment", show_header=True, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for check in checks:
        status = "[green]OK[/green]" if check["ok"] else "[red]MISSING[/red]"
        detail = str(check["detail"])
        table.add_row(str(check["name"]), status, detail)
    console.print(table)
    if all(check["ok"] for check in checks):
        console.print("\n[green]Ready to benchmark.[/green]")
    else:
        console.print("\n[red]Not ready; resolve the failing checks above.[/red]")
        raise typer.Exit(1)
