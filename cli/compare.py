"""benching compare — run and compare two or more providers."""
from __future__ import annotations

import typer
from rich.console import Console

from benchmark._paths import DEFAULT_CONCURRENCY, DEFAULT_TRIALS
from benchmark.config import benchmark_spec, enabled_providers, load_yaml
from benchmark.runner import analyze_runs, compare as compare_runs

app = typer.Typer(help="Run and compare providers.", no_args_is_help=True)
console = Console()


@app.command()
def compare(
    providers: list[str] = typer.Argument(..., metavar="PROVIDER", help="Providers to compare (two or more)"),
    smoke: bool = typer.Option(False, "--smoke", help="Run the smoke subset instead of the full suite"),
    execution: str = typer.Option("sequential", "--execution", help="sequential (official) or parallel (informal)"),
    model: str | None = typer.Option(None, "--model", help="Override benchmark.model (must match config)"),
    reasoning: str = typer.Option("default", "--reasoning", help="Reasoning mode"),
    concurrency: int = typer.Option(DEFAULT_CONCURRENCY, "--concurrency", help="Concurrent agent tasks"),
    trials: int = typer.Option(DEFAULT_TRIALS, "--trials", help="Attempts per task"),
) -> None:
    """Run PROVIDERs and build a comparison report."""
    if len(providers) < 2:
        raise typer.BadParameter("compare needs at least two providers")
    if execution not in ("sequential", "parallel"):
        raise typer.BadParameter("--execution must be sequential or parallel")
    root = load_yaml()
    spec = benchmark_spec(root)
    configured = set(enabled_providers(root))
    unknown = [name for name in providers if name not in configured]
    if unknown:
        raise typer.BadParameter(f"provider(s) not enabled: {', '.join(unknown)} (enabled: {', '.join(sorted(configured)) or 'none'})")
    mode = "smoke" if smoke else "full"
    console.print(f"[bold]{spec.display_name}[/bold] — comparing {', '.join(providers)} ({execution})")
    try:
        directories = compare_runs(providers, mode, model, concurrency, trials, root, execution=execution, reasoning=reasoning)
        analyze_runs(directories, execution=execution)
    except SystemExit as exc:
        console.print("[red]Comparison failed[/red]")
        raise typer.Exit(1 if isinstance(exc.code, int) else exc.code or 1) from exc
    console.print("[green]Comparison complete[/green]")
