"""benching config — inspect the active configuration."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from benchmark.config import benchmark_spec
from benchmark.state import load_state

app = typer.Typer(help="Inspect benching configuration.", no_args_is_help=True)
console = Console()


@app.command()
def show() -> None:
    """Show the active benchmark, providers, and user defaults."""
    from benchmark.benchmarks import active_root_config

    root = active_root_config()
    spec = benchmark_spec(root)

    suite = Table(title="Benchmark suite", show_header=False, box=None)
    suite.add_column("Key", style="bold")
    suite.add_column("Value")
    for key, value in (
        ("Name", spec.name),
        ("Version", spec.version),
        ("Model", spec.model),
        ("Reasoning", spec.reasoning),
        ("Tasks dir", str(spec.tasks_dir)),
        ("Expected tasks", str(spec.expected_task_count) if spec.expected_task_count is not None else "unset"),
        ("Smoke tasks", ", ".join(spec.smoke_tasks) or "unset"),
        ("Agent", spec.agent),
        ("Run id prefix", spec.run_id_prefix),
        ("Tokenizer", f"{spec.tokenizer_repo} @ {spec.tokenizer_revision[:12]}"),
    ):
        suite.add_row(key, value)
    console.print(suite)

    providers = Table(title="Providers", show_header=True, header_style="bold")
    providers.add_column("Name", style="bold")
    providers.add_column("Enabled")
    providers.add_column("Model")
    providers.add_column("Base URL")
    for name in sorted((root.get("providers") or {})):
        cfg = root["providers"][name]
        providers.add_row(name, "yes" if cfg.get("enabled") else "no", str(cfg.get("api_model") or ""), str(cfg.get("base_url") or ""))
    console.print(providers)

    state = load_state()
    user = Table(title="User defaults", show_header=False, box=None)
    user.add_column("Key", style="bold")
    user.add_column("Value")
    for key, value in (
        ("Active provider", state.active_provider or "unset"),
        ("Active benchmark", state.active_benchmark or "repo default"),
        ("Model override", state.model or "benchmark default"),
        ("Concurrency", str(state.concurrency)),
        ("Trials", str(state.trials)),
        ("Reasoning", state.reasoning),
    ):
        user.add_row(key, value)
    console.print(user)
