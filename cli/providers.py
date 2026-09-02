"""benching provider — list, validate, and probe providers."""
from __future__ import annotations

import json
import os
import shutil

import typer
from rich.console import Console
from rich.table import Table

from benchmark._paths import RUNS
from benchmark.config import (
    benchmark_spec,
    enabled_providers,
    load_yaml,
    provider_env_values,
    resolve,
)
from benchmark.concurrency import probe_provider
from benchmark.validation import classify_validation, validate_provider, write_validation_report

app = typer.Typer(help="Manage benchmark providers.", no_args_is_help=True)
console = Console()


def _status_for(name: str, cfg: dict) -> str:
    """Local configuration status: configured | missing credentials | missing env."""
    env_file = cfg.get("env_file")
    if not isinstance(env_file, str) or not env_file:
        return "no env file"
    env_values = provider_env_values(name, cfg)
    key = env_values.get(str(cfg.get("auth_env", "")))
    return "missing credentials" if not key else "configured"


@app.command("list")
def list_providers() -> None:
    """List configured providers with model and credential status."""
    root = load_yaml()
    spec = benchmark_spec(root)
    providers = root.get("providers") or {}
    table = Table(title="Providers", show_header=True, header_style="bold")
    table.add_column("NAME", style="bold")
    table.add_column("MODEL")
    table.add_column("STATUS")
    table.add_column("ENABLED")
    for name in sorted(providers):
        cfg = providers[name]
        status = _status_for(name, cfg)
        table.add_row(name, str(cfg.get("api_model") or ""), status, "yes" if cfg.get("enabled") else "no")
    console.print(table)
    if not providers:
        console.print("[yellow]No providers configured; add entries under providers: in config/benchmark.yaml[/yellow]")


@app.command("validate")
def validate(provider: str) -> None:
    """Validate a provider's credentials and streaming model access."""
    root = load_yaml()
    spec = benchmark_spec(root)
    configured = set(enabled_providers(root))
    if provider not in configured:
        raise typer.BadParameter(f"provider is not enabled: {provider} (enabled: {', '.join(sorted(configured)) or 'none'})")
    console.print(f"Validating [bold]{provider}[/bold]...", end="")
    try:
        result = validate_provider(provider, spec, root)
    except SystemExit as exc:
        console.print(" [red]failed[/red]")
        raise typer.Exit(1) from exc
    output = write_validation_report(provider, result)
    console.print(" [green]done[/green]")
    if not result["success"]:
        console.print(f"[red]Validation failed[/red] ({result['error_class']}); see {output}")
        raise typer.Exit(1)
    console.print(json.dumps(result, indent=2))
    console.print(f"\nReport: [cyan]{output}[/cyan]")


@app.command("probe")
def probe(
    provider: str,
    stages: str = typer.Option("2,3,5,6", help="Comma-separated concurrency levels to probe"),
) -> None:
    """Probe a provider's concurrency ceiling with staged concurrent streams."""
    root = load_yaml()
    spec = benchmark_spec(root)
    configured = set(enabled_providers(root))
    if provider not in configured:
        raise typer.BadParameter(f"provider is not enabled: {provider} (enabled: {', '.join(sorted(configured)) or 'none'})")
    stage_values = tuple(int(value.strip()) for value in stages.split(",") if value.strip())
    if not stage_values:
        raise typer.BadParameter("--stages must contain at least one level")
    console.print(f"Probing [bold]{provider}[/bold] concurrency at {', '.join(map(str, stage_values))}...")
    try:
        summary_path, jsonl_path = probe_provider(provider, spec, root, stages=stage_values)
    except SystemExit as exc:
        raise typer.Exit(1) from exc
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    console.print(f"[green]Highest verified concurrency:[/green] {summary['highest_verified_concurrency']}")
    if summary.get("first_rejected_concurrency") is not None:
        console.print(f"First rejected: {summary['first_rejected_concurrency']} (status {summary.get('rejection_status')})")
    console.print(f"Summary: [cyan]{summary_path}[/cyan]")
    console.print(f"Requests: [cyan]{jsonl_path}[/cyan]")
