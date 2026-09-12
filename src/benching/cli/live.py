"""benching live renderer — Rich terminal UI owned by the CLI layer.

Reusable benchmark code exposes structured progress (:class:`ProgressEvent`,
``ProgressFn``, :class:`RunProgress`) and owns process lifecycle/cleanup;
this module owns all Rich rendering (Live, tables, layout, refresh).
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

from benching.benchmark.runner import RunProgress, _read_live_metrics
from benching.benchmark.status import ProgressEvent

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
    """Accumulates structured progress events into render state."""

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
        elif event.phase in {"task_completed", "task_failed", "task_timed_out", "done"} and event.phase != "done":
            self.done = max(self.done, event.completed)
            self.passed = max(self.passed, event.passed)
            self.failed = max(self.failed, event.failed)
            self.running = max(0, self.total - self.done)

    def reconcile(self, snapshot: dict[str, Any]) -> None:
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
        return Group(*parts) if parts else Text("")


def drive_live_view(
    on_start: Callable[[], Any],
    *,
    title: str = "",
    poll_harbor: bool = True,
    poll_interval: float = 0.3,
    cancel: threading.Event | None = None,
    worker_join_timeout: float | None = None,
) -> Any:
    """Run a benchmark worker while rendering structured live progress.

    ``cancel`` is the cancellation event shared with orchestration (callers
    pass the same event they give to ``run_one``). On foreground Ctrl+C the
    event is set, run-owned children are terminated directly from this
    thread as well (the worker may be blocked), the worker is joined with a
    bounded wait, and ``SystemExit(130)`` propagates. No daemon worker or
    run-owned process escapes after foreground exit.

    The UI layer initiates cancellation; actual owned-resource cleanup
    remains core lifecycle responsibility
    (:mod:`benching.benchmark.lifecycle`).
    """
    from benching.benchmark.lifecycle import LIVE_WORKER_JOIN_TIMEOUT, terminate_all_active

    if worker_join_timeout is None:
        worker_join_timeout = LIVE_WORKER_JOIN_TIMEOUT
    console = Console()
    if title:
        console.print(title)
    state = LiveRunState()
    events: queue.Queue[ProgressEvent] = queue.Queue()
    result: dict = {}
    owned_cancel = cancel if cancel is not None else threading.Event()

    def on_event(event: ProgressEvent) -> None:
        events.put(event)

    def worker() -> None:
        try:
            result["value"] = on_start(on_event)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        with Live(console=console, refresh_per_second=5, screen=False) as live:
            while thread.is_alive() or not events.empty():
                changed = False
                while not events.empty():
                    state.handle(events.get_nowait())
                    changed = True
                if poll_harbor and state.jobs_dir is not None and state.jobs_dir.is_dir():
                    state.reconcile(RunProgress(state.jobs_dir, state.total, raw_jsonl=state.raw_path).refresh())
                if state.total or state.steps or changed:
                    live.update(state.renderable())
                time.sleep(poll_interval)
            live.update(state.renderable())
            thread.join(timeout=1)
    except KeyboardInterrupt:
        # Foreground interruption reaches orchestration: signal the worker's
        # run, terminate run-owned children from here too in case the worker
        # is blocked, then wait boundedly before propagating.
        owned_cancel.set()
        terminate_all_active()
        thread.join(timeout=worker_join_timeout)
        console.print("\n[red]Interrupted.[/red]")
        raise SystemExit(130) from None
    return result
