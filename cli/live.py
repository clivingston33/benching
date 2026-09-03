"""Shared live run view driver.

Renders the in-place progress view for both real runs (``benching run``)
and the synthetic demo (``benching demo``). Consumes structured
:class:`ProgressEvent` objects from a queue and reconciles task counters
against harbor result.json files when a run directory is present.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from benchmark.runner import RunProgress, _read_live_metrics
from benchmark.status import ProgressEvent

# Lifecycle preflight phases rendered as ✓ step lines.
STEP_PHASES = frozenset({"docker", "tokenizer", "validate", "proxy", "analyze"})


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def progress_bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return ""
    filled = int(round(done / total * width))
    return "█" * filled + "░" * (width - filled)


class LiveRunState:
    """Accumulates events into render state (steps + task counters)."""

    def __init__(self) -> None:
        self.steps: list[str] = []
        self.total = 0
        self.done = 0
        self.passed = 0
        self.failed = 0
        self.running = 0
        self.started_mono: float | None = None
        self.jobs_dir: Path | None = None
        self.raw_path: Path | None = None

    def handle(self, event: ProgressEvent) -> None:
        if event.phase in STEP_PHASES:
            self.steps.append(f"[green]✓[/green] {event.message}")
        elif event.phase == "running":
            self.total = event.total
            self.started_mono = self.started_mono or time.monotonic()
            if event.run_dir:
                base = Path(event.run_dir)
                self.jobs_dir = base / "harbor"
                self.raw_path = base / "raw.jsonl"
        elif event.phase in {"task_completed", "task_failed", "task_timed_out", "done"}:
            if event.phase != "done":
                self.done = max(self.done, event.completed)
                self.passed = max(self.passed, event.passed)
                self.failed = max(self.failed, event.failed)
                self.running = max(0, self.total - self.done)
            elif event.elapsed_seconds:
                pass  # done carries final counters; keep them

    def reconcile(self, snapshot: dict[str, Any]) -> None:
        """Overwrite counters from harbor-results polling (authoritative)."""
        self.done = snapshot["completed"]
        self.passed = snapshot["passed"]
        self.failed = snapshot["failed"]
        self.running = snapshot["running"]

    def renderable(self) -> Group | Text:
        parts: list[object] = [Text.from_markup(step) for step in self.steps]
        if self.total:
            bar = progress_bar(self.done, self.total)
            elapsed = (time.monotonic() - self.started_mono) if self.started_mono else 0.0
            lines = [
                f"[bold]Running[/bold]  [cyan]{bar}[/cyan]  [bold]{self.done} / {self.total}[/bold]",
                "",
                f"  Passed   [green]{self.passed}[/green]",
                f"  Failed   [red]{self.failed}[/red]",
                f"  Running  [yellow]{self.running}[/yellow]",
                f"  Elapsed  {fmt_duration(elapsed)}",
            ]
            if self.raw_path:
                ttft, tps = _read_live_metrics(self.raw_path)
                if ttft is not None:
                    lines.append(f"  TTFT       [magenta]{ttft:g} ms[/magenta]")
                if tps is not None:
                    lines.append(f"  Decode TPS [magenta]{tps:g}[/magenta]")
            parts.append(Panel(Text.from_markup("\n".join(lines)), title="Benchmark progress", border_style="cyan"))
        if not parts:
            return Text("")
        return Group(*parts)


def drive_live_view(
    on_start: Callable[[], Any],
    *,
    title: str = "",
    poll_harbor: bool = True,
    poll_interval: float = 0.3,
) -> Any:
    """Run ``on_start`` (typically a worker thread launcher) with a live view.

    Returns the ``result`` dict populated by ``on_start`` (expected to set
    ``result["directory"]`` or ``result["error"]``). Raises SystemExit(130)
    on KeyboardInterrupt.
    """
    console = Console()
    if title:
        console.print(title)
    state = LiveRunState()
    events: queue.Queue[ProgressEvent] = queue.Queue()
    result: dict = {}

    def on_event(event: ProgressEvent) -> None:
        events.put(event)

    def worker() -> None:
        try:
            result["value"] = on_start(on_event)
        except BaseException as exc:  # noqa: BLE001 — surfaced on main thread
            result["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        with Live(console=console, refresh_per_second=5, screen=False) as live:
            while thread.is_alive() or not events.empty():
                changed = False
                while not events.empty():
                    event = events.get_nowait()
                    state.handle(event)
                    changed = True
                if poll_harbor and state.jobs_dir is not None and state.jobs_dir.is_dir():
                    snapshot = RunProgress(state.jobs_dir, state.total, raw_jsonl=state.raw_path).refresh()
                    state.reconcile(snapshot)
                if state.total or state.steps or changed:
                    live.update(state.renderable())
                time.sleep(poll_interval)
            live.update(state.renderable())
            thread.join(timeout=1)
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted.[/red]")
        raise SystemExit(130) from None
    return result
