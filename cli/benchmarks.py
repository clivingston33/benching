"""benching benchmark — manage the local benchmark registry."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from benchmark.state import load_state

app = typer.Typer(help="Manage the benchmark registry.", no_args_is_help=True)
console = Console()


@app.command("list")
def list_benchmarks() -> None:
    """List registered benchmarks; * marks the active one."""
    from benchmark.benchmarks import list_benchmarks as all_benchmarks

    entries = all_benchmarks()
    active = load_state().active_benchmark
    if not entries:
        console.print("[yellow]No benchmarks registered; run `benching benchmark add`.[/yellow]")
        return
    table = Table(title="Benchmarks", show_header=True, header_style="bold")
    table.add_column("", width=2)
    table.add_column("NAME", style="bold")
    table.add_column("SUITE")
    table.add_column("TASKS")
    for entry in entries:
        table.add_row("*" if entry["name"] == active else "", entry["name"], str(entry["display"]), str(entry["expected_task_count"] or "?"))
    console.print(table)


@app.command("add")
def add(
    name: str = typer.Option(..., "--name", prompt=True, help="Registry name (e.g. terminal-bench-2.1)"),
    suite: str = typer.Option(..., "--suite", prompt=True, help="Display name of the suite (e.g. Terminal-Bench)"),
    version: str = typer.Option(..., "--version", prompt=True, help="Suite version"),
    tasks_dir: str = typer.Option(..., "--tasks-dir", prompt=True, help="Path to the local Harbor tasks directory"),
    agent: str = typer.Option("agents.instrumented_omp_agent:InstrumentedOmpAgent", "--agent", help="Agent module:Class"),
    model: str = typer.Option("", "--model", help="Model id the suite targets (defaults to the provider's model)"),
    expected_task_count: int = typer.Option(None, "--expected-task-count", help="Fail if the dir holds a different count"),
    smoke_tasks: str = typer.Option("", "--smoke-tasks", help="Comma-separated smoke subset"),
    tokenizer_repo: str = typer.Option("", "--tokenizer-repo", help="Pinned HF tokenizer repo"),
    tokenizer_revision: str = typer.Option("", "--tokenizer-revision", help="Pinned HF tokenizer revision"),
) -> None:
    """Register a local Harbor task directory as a benchmark."""
    from benchmark.benchmarks import add_benchmark
    from benchmark.config import benchmark_spec, load_yaml

    defaults = benchmark_spec(load_yaml())
    settings = {
        "name": suite,
        "version": version,
        "tasks_dir": tasks_dir,
        "agent": agent,
        "model": model or defaults.model,
        "reasoning": defaults.reasoning,
        "max_tokens": defaults.max_tokens,
        "context_window": defaults.context_window,
        "run_id_prefix": name,
        "expected_task_count": expected_task_count,
        "smoke_tasks": [task.strip() for task in smoke_tasks.split(",") if task.strip()],
        "tokenizer": {
            "repo": tokenizer_repo or defaults.tokenizer_repo,
            "revision": tokenizer_revision or defaults.tokenizer_revision,
        },
    }
    if (tokenizer_repo and not tokenizer_revision) or (tokenizer_revision and not tokenizer_repo):
        raise typer.BadParameter("--tokenizer-repo and --tokenizer-revision go together")
    try:
        path = add_benchmark(name, settings)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Benchmark added: [cyan]{name}[/cyan] ({path})")


@app.command("remove")
def remove(name: str = typer.Argument(..., help="Benchmark to remove")) -> None:
    """Remove a benchmark from the registry."""
    from benchmark.benchmarks import remove_benchmark

    try:
        remove_benchmark(name)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Benchmark removed: [cyan]{name}[/cyan]")


@app.command("use")
def use(name: str = typer.Argument(..., help="Benchmark to activate")) -> None:
    """Make a benchmark the active one."""
    from benchmark.benchmarks import set_active_benchmark

    try:
        manifest = set_active_benchmark(name)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    settings = manifest.get("benchmark") or {}
    tasks = settings.get("expected_task_count") or "?"
    display = f"{settings.get('name', name)} {settings.get('version', '')}".strip()
    console.print(f"[green]✓[/green] Benchmark: {display} · {tasks} tasks")


@app.command("info")
def info(name: str = typer.Argument(..., help="Benchmark to inspect")) -> None:
    """Show one benchmark manifest."""
    from benchmark.benchmarks import load_manifest

    try:
        manifest = load_manifest(name)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(manifest)
