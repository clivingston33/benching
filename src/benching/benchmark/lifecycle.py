"""Run lifecycle ownership for benchmark execution (M1 task 3).

Every benchmark run explicitly owns the processes, port, proxy requests,
and cleanup it creates. This module holds the small shared pieces:

- supported execution platform gate (Linux/WSL-only for runs)
- per-run proxy authentication token generation
- :class:`RunHandle`: the Harbor process, proxy process, run directory,
  proxy port, auth token, and cancellation state owned by one run
- Windows-safe bounded process termination (TERM → KILL escalation)
- interruptible child waiting that observes cancellation
- a registry of live handles so a foreground Ctrl+C can terminate
  run-owned children even when orchestration runs on a worker thread

No global process searching, no name-based cleanup, no port broker.
Analysis/result-reading commands stay portable; only execution is gated.
"""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Set to "1" to exercise orchestration mechanics with mocked processes on
#: an otherwise unsupported platform (unit tests only). Real benchmark
#: execution still requires Linux/WSL with Docker + Harbor + OMP.
ALLOW_UNSUPPORTED_PLATFORM_ENVVAR = "BENCHING_ALLOW_UNSUPPORTED_PLATFORM"

#: Bounded waits. Harbor normal completion is unbounded by design (a suite
#: takes as long as it takes); every *shutdown* wait below is bounded.
PROXY_STARTUP_TIMEOUT = 10.0
PROCESS_STOP_GRACE = 5.0
LIVE_WORKER_JOIN_TIMEOUT = 30.0


def is_supported_execution_platform() -> bool:
    """True on platforms where run lifecycle semantics are known to work."""
    return os.name != "nt"


def require_supported_execution_platform() -> None:
    """Fail fast on native Windows instead of implying supported execution.

    Raises ``SystemExit`` with recovery guidance. Analysis, results, and
    dashboard commands remain portable; only run execution is gated.
    """
    if is_supported_execution_platform():
        return
    if os.environ.get(ALLOW_UNSUPPORTED_PLATFORM_ENVVAR) == "1":
        return
    raise SystemExit(
        "benchmark execution requires Linux or WSL with Docker, Harbor, and OMP; "
        "native Windows does not support the run lifecycle (process groups, "
        "signal handling, container networking). Analysis commands "
        "(runs, results, tokenizer, provider list) remain available on Windows."
    )


def new_proxy_token() -> str:
    """Generate a cryptographically random per-run proxy auth token."""
    return secrets.token_urlsafe(32)


def _terminate(process: subprocess.Popen[bytes], grace: float) -> None:
    """Terminate one child with bounded TERM → KILL escalation, cross-platform."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Native Windows has no process groups via os.killpg.
        try:
            process.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except (ProcessLookupError, PermissionError, OSError):
                return
            try:
                process.wait(timeout=grace)
            except (subprocess.TimeoutExpired, OSError):
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            process.wait(timeout=grace)
        except (subprocess.TimeoutExpired, OSError):
            pass


def stop_process(process: subprocess.Popen[bytes] | None, grace: float = PROCESS_STOP_GRACE) -> None:
    """Stop one owned child process with bounded graceful → forceful escalation.

    Operates only on the given handle. Never searches for or signals
    unrelated processes.
    """
    if process is None:
        return
    _terminate(process, grace)


def spawn_owned(
    argv: list[str],
    *,
    cwd: Path | str | None,
    env: dict[str, str] | None = None,
    stdout: Any = None,
    stderr: Any = None,
) -> subprocess.Popen[bytes]:
    """Spawn a run-owned child with platform-appropriate process grouping.

    ``cwd=None`` inherits the invoker's working directory. All launch
    arguments elsewhere are absolute, so no caller depends on a
    repository-relative working directory.
    """
    resolved = None if cwd is None else str(cwd)
    if os.name == "nt":
        return subprocess.Popen(
            argv,
            cwd=resolved,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    return subprocess.Popen(
        argv,
        cwd=resolved,
        env=env,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )


@dataclass
class RunHandle:
    """Explicit ownership record for one benchmark run.

    Knows the Harbor child, the proxy child, the run directory, the proxy
    port, the per-run proxy auth token, and the cancellation state. All
    cleanup acts only on these registered handles.
    """

    provider: str = ""
    directory: Path | None = None
    proxy_port: int = 0
    auth_token: str = ""
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    proxy: subprocess.Popen[bytes] | None = None
    harbor: subprocess.Popen[bytes] | None = None

    def register_proxy(self, process: subprocess.Popen[bytes] | None) -> None:
        with self.lock:
            self.proxy = process

    def register_harbor(self, process: subprocess.Popen[bytes] | None) -> None:
        with self.lock:
            self.harbor = process

    def request_cancel(self) -> None:
        self.cancel_requested.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_requested.is_set()

    def owned_processes(self) -> list[subprocess.Popen[bytes]]:
        with self.lock:
            return [p for p in (self.harbor, self.proxy) if p is not None]

    def terminate_owned(self, grace: float = PROCESS_STOP_GRACE) -> None:
        """Stop owned children (Harbor first, then proxy) with bounded waits.

        Never touches processes outside this handle.
        """
        for process in self.owned_processes():
            stop_process(process, grace)

    def all_owned_exited(self) -> bool:
        return all(p.poll() is not None for p in self.owned_processes())


def wait_owned(handle: RunHandle, grace_poll: float = 0.05) -> int:
    """Wait for the handle's Harbor child, observing cancellation and proxy life.

    Returns the Harbor exit code. Raises ``KeyboardInterrupt`` when
    ``cancel_requested`` is set so cancellation stays distinguishable
    from provider/Harbor failure. Raises ``SystemExit`` without waiting
    further when the owned proxy dies mid-run: Harbor must not keep
    sending telemetry into a dead port (or a stranger's listener).
    """
    harbor = handle.harbor
    if harbor is None:
        raise SystemExit("run has no owned Harbor process")
    while True:
        if handle.cancelled:
            raise KeyboardInterrupt
        if harbor.poll() is not None:
            return int(harbor.poll())
        with handle.lock:
            proxy_proc = handle.proxy
        if proxy_proc is not None and proxy_proc.poll() is not None:
            raise SystemExit("owned telemetry proxy died during the run")
        try:
            return harbor.wait(timeout=grace_poll)
        except subprocess.TimeoutExpired:
            continue


_ACTIVE_LOCK = threading.Lock()
_ACTIVE_RUNS: set[int] = set()
_ACTIVE_HANDLES: dict[int, RunHandle] = {}


def track(handle: RunHandle):
    """Context manager registering a handle while its run is active."""

    class _Tracker:
        def __enter__(self) -> RunHandle:
            with _ACTIVE_LOCK:
                _ACTIVE_RUNS.add(id(handle))
                _ACTIVE_HANDLES[id(handle)] = handle
            return handle

        def __exit__(self, *exc: Any) -> None:
            with _ACTIVE_LOCK:
                _ACTIVE_RUNS.discard(id(handle))
                _ACTIVE_HANDLES.pop(id(handle), None)

    return _Tracker()


def terminate_all_active(grace: float = PROCESS_STOP_GRACE) -> None:
    """Terminate children of every currently tracked run handle.

    Used by the foreground on Ctrl+C when orchestration runs on a worker
    thread: it touches only handles created by this process's own runs,
    never unrelated processes.
    """
    with _ACTIVE_LOCK:
        handles = list(_ACTIVE_HANDLES.values())
    for handle in handles:
        try:
            handle.terminate_owned(grace)
        except OSError:
            pass
