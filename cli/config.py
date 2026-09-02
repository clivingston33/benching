"""benching config — inspect the active configuration."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from benchmark.config import benchmark_spec, enabled_providers, load_yaml

app = typer.Typer(help="Inspect benching configuration.", no_args_is_help=True)
console = Console()


@app.command()
def show() -> None:
    """Show the benchmark suite and provider registry."""
    root = load_yaml()
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
    for name in sorted(enabled_providers(root) + [name for name in (root.get("providers") or {}) if name not in enabled_providers(root)]):
        cfg = root["providers"][name]
        providers.add_row(name, "yes" if cfg.get("enabled") else "no", str(cfg.get("api_model") or ""), str(cfg.get("base_url") or ""))
    console.print(providers)
