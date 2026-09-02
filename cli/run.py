"""benching run — execute a benchmark run for one provider with a live view."""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from benchmark._paths import DEFAULT_CONCURRENCY, DEFAULT_TRIALS
from benchmark.config import benchmark_spec, enabled_providers, load_yaml
from benchmark.runner import RunOptions, RunProgress, _read_live_metrics, run_one
from benchmark.status import ProgressEvent

app = typer.Typer(help="Run the benchmark suite against one provider.", no_args_is_help=True)
console = Console()


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _progress_bar(done: int, total: int) -> str:
    if total <= 0:
        return ""
    width = 24
    filled = int(round(done / total * width))
    return "█" * filled + "░" * (width - filled)


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

    events: queue.Queue[ProgressEvent] = queue.Queue()
    result: dict = {}
    state: dict = {"steps": [], "total": 0, "done": 0, "passed": 0, "failed": 0, "running": 0, "started_mono": None, "jobs_dir": None, "raw_path": None}

    def on_event(event: ProgressEvent) -> None:
        events.put(event)

    def worker() -> None:
        try:
            directory = run_one(options, root, progress=on_event)
            result["directory"] = directory
        except BaseException as exc:  # noqa: BLE001 — surfaced on main thread
            result["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def build_renderable() -> Group:
        parts: list[object] = []
        for step in state["steps"]:
            parts.append(step)
        total = state["total"]
        if total:
            done = state["done"]
            passed = state["passed"]
            failed = state["failed"]
            running = state["running"]
            elapsed = (time.monotonic() - state["started_mono"]) if state["started_mono"] else 0.0
            bar = _progress_bar(done, total)
            lines = [
                f"[bold]Running[/bold]  [cyan]{bar}[/cyan]  [bold]{done} / {total}[/bold]",
                "",
                f"  Passed   [green]{passed}[/green]",
                f"  Failed   [red]{failed}[/red]",
                f"  Running  [yellow]{running}[/yellow]",
                f"  Elapsed  {_fmt_duration(elapsed)}",
            ]
            if state["raw_path"]:
                ttft, tps = _read_live_metrics(state["raw_path"])
                if ttft is not None:
                    lines.append(f"  TTFT       [magenta]{ttft:g} ms[/magenta]")
                if tps is not None:
                    lines.append(f"  Decode TPS [magenta]{tps:g}[/magenta]")
            parts.append(Panel(Text.from_markup("\n".join(lines)), title="Benchmark progress", border_style="cyan"))
        return Group(*parts) if parts else Text("")

    try:
        with Live(console=console, refresh_per_second=5, screen=False) as live:
            while thread.is_alive() or not events.empty():
                changed = False
                while not events.empty():
                    event = events.get_nowait()
                    if event.phase in {"docker", "tokenizer", "validate", "proxy"}:
                        state["steps"].append(Text.from_markup(f"[green]✓[/green] {event.message}"))
                        changed = True
                    elif event.phase == "validate" and "validated" in event.message:
                        state["total"] = event.total
                        changed = True
                    elif event.phase == "running":
                        state["total"] = event.total
                        state["started_mono"] = time.monotonic()
                        if event.run_dir:
                            base = Path(event.run_dir)
                            state["jobs_dir"] = base / "harbor"
                            state["raw_path"] = base / "raw.jsonl"
                        changed = True
                # Reconcile task counters from harbor results each tick.
                if state["jobs_dir"] is not None and state["jobs_dir"].is_dir():
                    snapshot = RunProgress(state["jobs_dir"], state["total"], raw_jsonl=state["raw_path"]).refresh()
                    state["done"], state["passed"], state["failed"], state["running"] = (
                        snapshot["completed"],
                        snapshot["passed"],
                        snapshot["failed"],
                        snapshot["running"],
                    )
                if state["total"] or state["steps"] or changed:
                    live.update(build_renderable())
                time.sleep(0.3)
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted.[/red]")
        raise typer.Exit(130) from None

    if "error" in result:
        console.print("[red]Run failed[/red]")
        raise typer.Exit(getattr(result["error"], "code", 1) or 1)
    console.print(f"\n[green]Run complete:[/green] [cyan]{result['directory']}[/cyan]")
