"""benching demo — run a synthetic benchmark for UI development."""
from __future__ import annotations

import typer
from rich.console import Console

from benchmark.demo import DemoRun
from cli.live import drive_live_view

app = typer.Typer(help="Run a synthetic benchmark to preview the UI without infra.", no_args_is_help=True)
console = Console()


@app.command()
def run(
    provider: str = typer.Option("acme", "--provider", help="Provider name to display"),
    tasks: int = typer.Option(10, "--tasks", min=1, max=200, help="Number of fake tasks"),
    failure_rate: float = typer.Option(0.2, "--failure-rate", min=0.0, max=1.0, help="Fraction of tasks that fail"),
    speed: float = typer.Option(0.4, "--speed", min=0.05, max=5.0, help="Seconds per fake task (lower = faster)"),
    seed: int = typer.Option(1, "--seed", help="Random seed for reproducible demo"),
    keep: bool = typer.Option(False, "--keep", help="Keep the fake run directory after the demo"),
) -> None:
    """Preview the live run view end to end with no Docker or API keys.

    Emits the same structured progress events as a real run and writes fake
    harbor results + telemetry, so the identical render path (progress bar,
    pass/fail counters, live TTFT/decode-TPS) is exercised.
    """
    demo = DemoRun(provider=provider, total=tasks, failure_rate=failure_rate, task_seconds=speed, seed=seed)
    title = f"[bold]Demo suite 1.0[/bold] — [cyan]{provider}[/cyan] (full, concurrency 3)"

    def start(on_event):
        for event in demo.events():
            on_event(event)
        return demo.directory

    result = drive_live_view(start, title=title)
    if "error" in result:
        console.print("[red]Demo failed[/red]")
        raise typer.Exit(1) from result["error"]
    directory = demo.directory
    if directory is not None:
        console.print(f"\n[green]Demo complete:[/green] [cyan]{directory}[/cyan]")
        if not keep:
            import shutil

            shutil.rmtree(directory, ignore_errors=True)
        else:
            console.print("Run directory kept (see `benching runs list` / `benching results show latest`).")
