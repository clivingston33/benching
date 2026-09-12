"""benching run — execute a benchmark run for one provider with a live view."""
from __future__ import annotations

import typer
from rich.console import Console

from benching.benchmark.runner import run_one
from benching.cli.live import drive_live_view

app = typer.Typer(help="Run the benchmark suite against one provider.", no_args_is_help=True)
console = Console()


@app.command()
def run(
    provider: str = typer.Argument(None, help="Provider to run (defaults to the active provider)"),
    smoke: bool = typer.Option(False, "--smoke", help="Run the quick smoke subset instead of the full suite"),
    model: str | None = typer.Option(None, "--model", help="Per-run provider model override"),
    reasoning: str | None = typer.Option(None, "--reasoning", help="Per-run reasoning mode"),
    concurrency: int | None = typer.Option(None, "--concurrency", min=1, help="Concurrent agent tasks"),
    trials: int | None = typer.Option(None, "--trials", min=1, help="Attempts per task"),
) -> None:
    """Run the suite against PROVIDER (smoke or full)."""
    from benching.benchmark.settings import run_options

    try:
        options, settings = run_options(
            "smoke" if smoke else "full",
            provider=provider,
            model=model,
            reasoning=reasoning,
            concurrency=concurrency,
            trials=trials,
        )
    except SystemExit as exc:
        raise typer.BadParameter(str(exc.code or exc)) from None
    title = f"[bold]{settings.spec.display_name}[/bold] — [cyan]{options.provider}[/cyan] ({options.mode}, concurrency {options.concurrency})"
    import threading

    cancel = threading.Event()

    def start(on_event):
        return run_one(options, settings.root, progress=on_event, cancel=cancel)

    result = drive_live_view(start, title=title, cancel=cancel)
    if "error" in result:
        console.print("[red]Run failed[/red]")
        raise typer.Exit(getattr(result["error"], "code", 1) or 1)
    directory = result.get("value")
    if directory is not None:
        console.print(f"\n[green]Run complete:[/green] [cyan]{directory}[/cyan]")
