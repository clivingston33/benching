"""benching run — execute a benchmark run for one provider."""
from __future__ import annotations

import typer
from rich.console import Console

from benchmark._paths import DEFAULT_CONCURRENCY, DEFAULT_TRIALS
from benchmark.config import benchmark_spec, enabled_providers, load_yaml
from benchmark.runner import RunOptions, run_one

app = typer.Typer(help="Run the benchmark suite against one provider.", no_args_is_help=True)
console = Console()


@app.command()
def run(
    provider: str,
    smoke: bool = typer.Option(False, "--smoke", help="Run the quick smoke subset instead of the full suite"),
    model: str | None = typer.Option(None, "--model", help="Override benchmark.model (must match config)"),
    reasoning: str = typer.Option("default", "--reasoning", help="Reasoning mode"),
    concurrency: int = typer.Option(DEFAULT_CONCURRENCY, "--concurrency", help="Concurrent agent tasks"),
    trials: int = typer.Option(DEFAULT_TRIALS, "--trials", help="Attempts per task"),
) -> None:
    """Run the suite against PROVIDER (smoke or full)."""
    root = load_yaml()
    spec = benchmark_spec(root)
    configured = set(enabled_providers(root))
    if provider not in configured:
        raise typer.BadParameter(f"provider is not enabled: {provider} (enabled: {', '.join(sorted(configured)) or 'none'})")
    mode = "smoke" if smoke else "full"
    options = RunOptions(
        provider=provider,
        mode=mode,
        benchmark_model=model,
        reasoning=reasoning,
        concurrency=concurrency,
        trials=trials,
    )
    console.print(f"[bold]{spec.display_name}[/bold] — [cyan]{provider}[/cyan] ({mode}, concurrency {concurrency})")
    try:
        directory = run_one(options, root)
    except SystemExit as exc:
        console.print("[red]Run failed[/red]")
        raise typer.Exit(1 if isinstance(exc.code, int) else exc.code or 1) from exc
    console.print(f"\n[green]Run complete:[/green] [cyan]{directory}[/cyan]")
