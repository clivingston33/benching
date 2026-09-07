"""benching provider — list, validate, and probe providers."""
from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from benchmark.config import benchmark_spec, enabled_providers, load_yaml, provider_env_values
from benchmark.concurrency import probe_provider
from benchmark.state import load_state
from benchmark.validation import validate_provider, write_validation_report
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
    providers = root.get("providers") or {}
    active = load_state().active_provider
    table = Table(title="Providers", show_header=True, header_style="bold")
    table.add_column("", width=2)
    table.add_column("NAME", style="bold")
    table.add_column("MODEL")
    table.add_column("STATUS")
    table.add_column("ENABLED")
    for name in sorted(providers):
        cfg = providers[name]
        status = _status_for(name, cfg)
        table.add_row("*" if name == active else "", name, str(cfg.get("api_model") or ""), status, "yes" if cfg.get("enabled") else "no")
    console.print(table)
    if not providers:
        console.print("[yellow]No providers configured; run `benching provider add`.[/yellow]")


@app.command("add")
def add(
    name: str = typer.Option(..., "--name", prompt=True, help="Provider name (e.g. openrouter)"),
    base_url: str = typer.Option(..., "--base-url", prompt=True, help="API base URL (e.g. https://openrouter.ai/api/v1)"),
    api_model: str = typer.Option(..., "--model", prompt=True, help="Model id the provider serves"),
    api_key: str = typer.Option("", "--api-key", help="API key (prompted hidden when omitted)"),
    api: str = typer.Option("openai-completions", "--api", help="API flavor"),
    strict_model_check: bool = typer.Option(False, "--strict-model-check", help="Require api_model in /models"),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip the post-add validation"),
) -> None:
    """Register a provider, store its key, validate, and make it active."""
    import getpass

    from benchmark.providers import add_provider

    if not api_key:
        api_key = getpass.getpass("API key: ")
    try:
        add_provider(name, base_url, api_model, api_key, api=api, strict_model_check=strict_model_check)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Provider added: [cyan]{name}[/cyan]")
    if no_validate:
        return
    console.print("Testing connection...")
    try:
        validate(name)
    except SystemExit as exc:
        console.print(f"[yellow]Provider added but validation failed: {exc.code or exc}[/yellow]")
    else:
        console.print("[green]✓ Authentication[/green]")
        console.print("[green]✓ Streaming response[/green]")


@app.command("remove")
def remove(name: str = typer.Argument(..., help="Provider to remove")) -> None:
    """Remove a provider and delete its credential file."""
    from benchmark.providers import remove_provider

    try:
        remove_provider(name)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Provider removed: [cyan]{name}[/cyan]")


@app.command("use")
def use(name: str = typer.Argument(..., help="Provider to activate")) -> None:
    """Make a provider the active one."""
    from benchmark.providers import set_active_provider

    try:
        set_active_provider(name)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Active provider: [cyan]{name}[/cyan]")


@app.command("edit")
def edit(
    name: str = typer.Argument(..., help="Provider to edit"),
    base_url: str = typer.Option(None, "--base-url", help="New base URL"),
    api_model: str = typer.Option(None, "--model", help="New model id"),
    api_key: str = typer.Option(None, "--api-key", help="Rotate the stored API key"),
) -> None:
    """Edit a provider's base URL, model, or API key."""
    from benchmark.providers import rename_key_field, update_provider

    changes = {}
    if base_url:
        changes["base_url"] = base_url
    if api_model:
        changes["api_model"] = api_model
    try:
        if changes:
            update_provider(name, **changes)
        if api_key:
            rename_key_field(name, api_key)
    except SystemExit as exc:
        console.print(f"[red]{exc.code or exc}[/red]")
        raise typer.Exit(1) from exc
    if not changes and not api_key:
        console.print("[yellow]Nothing to change; pass --base-url, --model, or --api-key.[/yellow]")
        return
    console.print(f"[green]✓[/green] Provider updated: [cyan]{name}[/cyan]")


@app.command("validate")
def validate(provider: str) -> None:
    """Validate a provider's credentials and streaming model access."""
    from benchmark.benchmarks import active_root_config

    root = active_root_config()
    spec = benchmark_spec(root)
    if provider not in enabled_providers(root):
        raise typer.BadParameter(f"provider is not enabled: {provider}")
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
    from benchmark.benchmarks import active_root_config

    root = active_root_config()
    spec = benchmark_spec(root)
    if provider not in enabled_providers(root):
        raise typer.BadParameter(f"provider is not enabled: {provider}")
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
