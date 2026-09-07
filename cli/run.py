"""benching run — execute a benchmark run for one provider with a live view."""
from __future__ import annotations

import typer
from rich.console import Console

from benchmark.config import benchmark_spec, enabled_providers
from benchmark.runner import RunOptions, run_one
from cli.live import drive_live_view

app = typer.Typer(help="Run the benchmark suite against one provider.", no_args_is_help=True)
console = Console()


@app.command()
def run(
    provider: str = typer.Argument(None, help="Provider to run (defaults to the active provider)"),
    smoke: bool = typer.Option(False, "--smoke", help="Run the quick smoke subset instead of the full suite"),
    model: str | None = typer.Option(None, "--model", help="Override benchmark.model (must match config)"),
    reasoning: str | None = typer.Option(None, "--reasoning", help="Reasoning mode"),
    concurrency: int | None = typer.Option(None, "--concurrency", min=1, help="Concurrent agent tasks"),
    trials: int | None = typer.Option(None, "--trials", min=1, help="Attempts per task"),
) -> None:
    """Run the suite against PROVIDER (smoke or full)."""
    from benchmark.benchmarks import active_root_config
    from benchmark.state import load_state

    state = load_state()
    provider = provider or state.active_provider
    if not provider:
        raise typer.BadParameter("no provider given and no active provider; run `benching provider use NAME` or pass PROVIDER")
    root = active_root_config()
    spec = benchmark_spec(root)
    configured = set(enabled_providers(root))
    if provider not in configured:
        raise typer.BadParameter(f"provider is not enabled: {provider} (enabled: {', '.join(sorted(configured)) or 'none'})")
    mode = "smoke" if smoke else "full"
    effective_reasoning = reasoning or state.reasoning
    effective_concurrency = concurrency or state.concurrency
    effective_trials = trials or state.trials
    options = RunOptions(
        provider=provider,
        mode=mode,
        benchmark_model=model or state.model,
        reasoning=effective_reasoning,
        concurrency=effective_concurrency,
        trials=effective_trials,
    )
    title = f"[bold]{spec.display_name}[/bold] — [cyan]{provider}[/cyan] ({mode}, concurrency {effective_concurrency})"

    def start(on_event):
        return run_one(options, root, progress=on_event)

    result = drive_live_view(start, title=title)
    if "error" in result:
        console.print("[red]Run failed[/red]")
        raise typer.Exit(getattr(result["error"], "code", 1) or 1)
    directory = result.get("value")
    if directory is not None:
        console.print(f"\n[green]Run complete:[/green] [cyan]{directory}[/cyan]")
