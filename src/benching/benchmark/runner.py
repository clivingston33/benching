"""Benchmark run execution: orchestrate Harbor runs behind the telemetry proxy."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benching.benchmark._paths import PROXY_PORT, ROOT, package_parent, runs_root
from benching.benchmark._util import utc
from benching.benchmark.config import (
    BenchmarkSpec,
    benchmark_spec,
    environment,
    load_yaml,
    provider_config,
    provider_env_values,
    resolve,
    resolve_model_settings,
)
from benching.benchmark.io import dump_json_atomic, write_text_atomic
from benching.benchmark.lifecycle import (
    PROXY_STARTUP_TIMEOUT,
    RunHandle,
    new_proxy_token,
    require_supported_execution_platform,
    spawn_owned,
    stop_process,
    track,
    wait_owned,
)
from benching.benchmark.security import write_credential_file
from benching.benchmark.status import ProgressEvent, ProgressFn, scan_harbor_results
from benching.benchmark.tokenizer import resolve_tokenizer_context, tokenizer_metadata
from benching.benchmark.validation import validate_provider

__all__ = [
    "RunOptions",
    "RunProgress",
    "run_directory",
    "harbor_command",
    "start_proxy",
    "stop_process",
    "set_status",
    "run_one",
    "compare",
    "analyze_runs",
]

# Progress lifecycle phases: docker, tokenizer, validate, proxy, running,
# analyze, done — plus per-task task_started/task_completed/task_failed/
# task_timed_out events carrying task-level fields (see benchmark.status).


def _noop_progress(event: ProgressEvent) -> None:
    return None


def _event(phase: str, message: str = "", **extra: Any) -> ProgressEvent:
    fields = {"phase": phase, "message": message}
    fields.update(extra)
    return ProgressEvent(**fields)


@dataclass(frozen=True)
class RunOptions:
    provider: str
    mode: str
    benchmark_model: str | None = None
    reasoning: str = "default"
    concurrency: int = 3
    trials: int = 1
    proxy_port: int = PROXY_PORT
    benchmark: BenchmarkSpec | None = None


def task_names(mode: str, spec: BenchmarkSpec) -> list[str]:
    """Resolve the task list for a mode: smoke uses smoke_tasks, full scans the dir."""
    if mode == "smoke":
        if not spec.smoke_tasks:
            raise SystemExit("smoke mode requires benchmark.smoke_tasks in the benchmark config")
        return list(spec.smoke_tasks)
    if mode != "full":
        raise SystemExit(f"unsupported mode: {mode}")
    if not spec.tasks_dir.is_dir():
        raise SystemExit(f"tasks directory not found: {spec.tasks_dir}")
    tasks = sorted(path.name for path in spec.tasks_dir.iterdir() if path.is_dir())
    if spec.expected_task_count is not None and len(tasks) != spec.expected_task_count:
        raise SystemExit(f"expected {spec.expected_task_count} tasks for {spec.display_name}, found {len(tasks)} in {spec.tasks_dir}")
    return tasks


def executable(name: str) -> str:
    """Locate a required executable without relying on mutated process state."""
    from benching.benchmark._paths import resolve_executable

    path = resolve_executable(name)
    if path is None:
        raise SystemExit(f"required executable not found: {name}")
    return str(path)


def version(name: str) -> str | None:
    from benching.benchmark._paths import resolve_executable

    path = resolve_executable(name)
    if path is None:
        return None
    try:
        completed = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text[:256] or None


def fingerprint(run: dict[str, Any]) -> str:
    """Digest of the run record for tamper-evidence, not environment equality.

    The hashed record includes run identity and timestamps, so equal
    fingerprints prove nothing about two runs sharing an environment.
    Never use this to claim identical execution environments.
    """
    encoded = json.dumps(run, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_directory(
    options: RunOptions,
    spec: BenchmarkSpec,
    config: dict[str, Any],
    endpoint: str,
    api_model: str,
    tasks: list[str],
    env_values: dict[str, str] | None = None,
    model_settings: dict[str, Any] | None = None,
    proxy_auth_token: str = "",
) -> Path:
    """Create the isolated runs/<run-id>/ directory and its immutable run.json.

    Also writes the private per-run proxy auth file (mode 0600). The token
    never enters run.json, summaries, or comparisons; the run directory is
    a private execution artifact, not a dashboard publication.
    """
    runs_root().mkdir(parents=True, exist_ok=True)
    run_id = f"{spec.run_id_prefix}-v1-{options.provider}-{options.mode}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = runs_root() / run_id
    directory.mkdir(parents=False)
    (directory / "harbor").mkdir()
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": utc(),
        "benchmark": spec.name,
        "benchmark_version": spec.version,
        "benchmark_model": spec.model or None,
        "model": api_model,
        "model_source": (model_settings or {}).get("sources", {}).get("model", "unknown"),
        "task_count": len(tasks),
        "tasks": tasks,
        "agent": spec.agent,
        "provider": options.provider,
        "provider_plan": config.get("plan"),
        "provider_plan_tier": config.get("plan_tier", "unknown"),
        "endpoint": endpoint,
        "api_model": api_model,
        "reasoning_mode": options.reasoning,
        "streaming": True,
        "concurrency": options.concurrency,
        "trials": options.trials,
        "automatic_provider_retries": 0,
        "task_attempts": options.trials,
        "harbor_version": version("harbor"),
        "omp_version": version("omp"),
        "python_version": platform.python_version(),
        "proxy_schema_version": 1,
        "effective_settings": {
            "model": api_model,
            "reasoning": options.reasoning,
            "endpoint": endpoint,
            "max_tokens": (model_settings or {}).get("max_tokens", spec.max_tokens),
            "context_window": (model_settings or {}).get("context_window", spec.context_window),
            "tokenizer_repo": (model_settings or {}).get("tokenizer_repo", spec.tokenizer_repo) or None,
            "tokenizer_revision": (model_settings or {}).get("tokenizer_revision", spec.tokenizer_revision) or None,
            "sources": (model_settings or {}).get("sources", {}),
        },
        "os": platform.platform(),
        "kernel": platform.release(),
        "cpu": platform.processor(),
        "tokenizer": tokenizer_metadata(spec, env_values, model_settings),
        "proxy_port": options.proxy_port,
    }
    run["environment_fingerprint"] = fingerprint(run)
    dump_json_atomic(directory / "run.json", run)
    routes = {options.provider: {"upstream": endpoint, "plan": config.get("plan"), "plan_tier": config.get("plan_tier", "unknown"), "reasoning": options.reasoning}}
    dump_json_atomic(directory / "proxy-routes.json", routes)
    write_credential_file(directory / "proxy-auth.json", json.dumps({"auth_token": proxy_auth_token}, indent=2) + "\n")
    dump_json_atomic(directory / "status.json", {"status": "created", "updated_at_utc": utc()})
    return directory


def harbor_command(
    options: RunOptions,
    spec: BenchmarkSpec,
    config: dict[str, Any],
    endpoint: str,
    api_model: str,
    directory: Path,
    tasks: list[str],
    model_settings: dict[str, Any] | None = None,
    proxy_auth_token: str = "",
) -> list[str]:
    """Build the Harbor run command that executes the suite in Docker.

    ``proxy_auth_token`` is the run-scoped proxy credential the agent must
    present with each proxy request. It lives in the private run directory
    (command.json, proxy-auth.json), never in summaries or comparisons.
    """
    command = [
        executable("harbor"), "run", "--path", str(spec.tasks_dir),
        "--agent", spec.agent,
        "--model", f"{options.provider}/{api_model}",
        "--jobs-dir", str(directory / "harbor"), "--job-name", directory.name,
        "--n-attempts", str(options.trials), "--n-concurrent", str(options.concurrency),
        "--n-concurrent-agents", str(options.concurrency), "--max-retries", "0",
        "--agent-include-logs", "**/*",
        "--mounts", json.dumps([{"type": "bind", "source": str(ROOT / "cache"), "target": "/opt/omp-cache", "read_only": True}]),
        "--extra-docker-compose", str(directory / "docker-host-gateway.yaml"),
    ]
    agent_kwargs = {
        "provider": options.provider,
        "provider_plan": config.get("plan") or "",
        "benchmark_model": api_model,
        "model": api_model,
        "upstream": endpoint,
        "api_key_env": config["auth_env"],
        "run_id": directory.name,
        "proxy_url": f"http://host.docker.internal:{options.proxy_port}",
        "proxy_auth_token": proxy_auth_token,
        "api": config.get("api", "openai-completions"),
        "reasoning": options.reasoning,
    }
    settings = model_settings or {}
    for key in ("max_tokens", "context_window"):
        value = settings.get(key, getattr(spec, key))
        if value is not None:
            agent_kwargs[key] = str(value)
    for key, value in agent_kwargs.items():
        command.extend(["--agent-kwarg", f"{key}={value}"])
    for task in tasks:
        command.extend(["--include-task-name", task])
    return command


def _proxy_health_ok(port: int, auth_token: str, timeout: float = 2.0) -> bool:
    """Authenticated readiness probe: only this run's proxy child can answer.

    A bare TCP connect is NOT sufficient (H2): any stale or unrelated
    listener would pass it. The probe requires the per-run secret, so a
    foreign listener holding the port fails the check and the run fails
    closed instead of hijacking another proxy's telemetry. Never logs
    the token.
    """
    from benching.proxy.telemetry_proxy import HEALTH_PATH, PROXY_AUTH_HEADER

    request = (
        f"GET {HEALTH_PATH} HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        f"{PROXY_AUTH_HEADER}: {auth_token}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin1")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(request)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
    except OSError:
        return False
    if b"\r\n\r\n" not in data:
        return False
    head, _, body = data.partition(b"\r\n\r\n")
    if b" 200 " not in head.split(b"\r\n", 1)[0]:
        return False
    return b'"ok":true' in body.replace(b" ", b"")


def _stderr_tail(path: Path, limit: int = 500) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    tail = text[-limit:].strip()
    return f": {tail}" if tail else ""


def start_proxy(
    directory: Path,
    port: int = PROXY_PORT,
    auth_token: str = "",
    timeout: float = PROXY_STARTUP_TIMEOUT,
) -> subprocess.Popen[bytes]:
    """Launch the run-owned telemetry proxy and prove it owns the port.

    Fails closed when the port is occupied, a stale proxy holds it, or the
    child exits immediately: Harbor must never start against an unverified
    proxy. Cancellation during startup leaves no stale process behind.
    """
    require_supported_execution_platform()
    if not auth_token:
        raise SystemExit("proxy auth token is required")
    auth_file = directory / "proxy-auth.json"
    if not auth_file.is_file():
        raise SystemExit(f"proxy auth file missing: {auth_file}")
    command = [
        sys.executable, "-m", "benching.proxy.telemetry_proxy",
        "--events", str(directory / "raw.jsonl"),
        "--routes", str(directory / "proxy-routes.json"),
        "--auth-token-file", str(auth_file),
        "--port", str(port),
    ]
    stdout_fh = (directory / "proxy.stdout.log").open("wb")
    stderr_fh = (directory / "proxy.stderr.log").open("wb")
    try:
        process = spawn_owned(
            command, cwd=None,
            env={**os.environ, "PYTHONPATH": str(package_parent())},
            stdout=stdout_fh, stderr=stderr_fh,
        )
    finally:
        stdout_fh.close()
        stderr_fh.close()
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit(
                    f"proxy failed to start; see {directory / 'proxy.stderr.log'}"
                    f"{_stderr_tail(directory / 'proxy.stderr.log')}"
                )
            if _proxy_health_ok(port, auth_token):
                return process
            time.sleep(0.1)
    except BaseException:
        stop_process(process)
        raise
    stop_process(process)
    raise SystemExit(f"proxy did not become ready within {timeout:g} seconds")


#: Artifacts that must exist (and, for summary.json, parse) before a run
#: may claim ``completed``. A comparison artifact never gates an
#: individual run's completion.
REQUIRED_COMPLETION_ARTIFACTS = ("run.json", "status.json", "metrics.jsonl", "summary.json")

COMMAND_TOKEN_PLACEHOLDER = "[REDACTED]"


def set_status(directory: Path, status: str, **extra: Any) -> None:
    dump_json_atomic(directory / "status.json", {"status": status, "updated_at_utc": utc(), **extra})


def _safe_set_status(directory: Path | None, status: str, **extra: Any) -> None:
    """Best-effort terminal status; cleanup errors must not mask the cause."""
    if directory is None:
        return
    try:
        set_status(directory, status, **extra)
    except Exception:
        pass


def _short_error(exc: BaseException) -> str:
    """Concise failure cause for status evidence, without secrets.

    Never echoes command lines (the Harbor command carries the run's
    proxy auth token) — only the exception type, exit code, and a
    truncated first line.
    """
    if isinstance(exc, subprocess.CalledProcessError):
        return f"{type(exc).__name__}: exit {exc.returncode}"
    first = str(exc).strip().splitlines()
    detail = first[0][:200] if first and first[0] else ""
    return f"{type(exc).__name__}: {detail}".rstrip(": ")


def redacted_command(command: list[str], proxy_auth_token: str) -> list[str]:
    """Copy of a Harbor command with the proxy auth token replaced.

    ``command.json`` keeps full reproducibility information except the
    secret itself. Execution always uses the unredacted argv; only the
    persisted record is redacted.
    """
    if not proxy_auth_token:
        return list(command)
    needle = f"proxy_auth_token={proxy_auth_token}"
    return [
        element.replace(needle, f"proxy_auth_token={COMMAND_TOKEN_PLACEHOLDER}")
        if needle in element else element
        for element in command
    ]


def verify_completion_artifacts(directory: Path) -> None:
    """Check the completion requirements; raise SystemExit identifying gaps."""
    missing = [name for name in REQUIRED_COMPLETION_ARTIFACTS if not (directory / name).is_file()]
    if missing:
        raise SystemExit(f"missing required artifacts: {', '.join(missing)}")
    try:
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid summary.json: {type(exc).__name__}") from None
    if not isinstance(summary, dict):
        raise SystemExit("invalid summary.json: expected object")


@dataclass
class RunProgress:
    """Live task-run monitor: polls harbor job results and tails raw.jsonl.

    The CLI drives this from the foreground thread while run_one runs the
    harbor subprocess; ``refresh`` is safe to call repeatedly and emits no
    events (the caller decides when to repaint).
    """

    jobs_dir: Path
    total: int
    raw_jsonl: Path | None = None
    known_done: set[str] = field(default_factory=set)

    def refresh(self) -> dict[str, Any]:
        results = scan_harbor_results(self.jobs_dir)
        counts = {"passed": 0, "failed": 0, "timed_out": 0, "completed": 0}
        for result in results.values():
            outcome = result.get("outcome", "completed")
            counts["completed"] += 1
            if outcome == "passed":
                counts["passed"] += 1
            elif outcome == "timed_out":
                counts["timed_out"] += 1
            elif outcome == "failed":
                counts["failed"] += 1
        completed = counts["completed"]
        running = max(0, self.total - completed)
        return {
            "completed": completed,
            "total": self.total,
            "passed": counts["passed"],
            "failed": counts["failed"] + counts["timed_out"],
            "running": running,
            "results": results,
        }


def _read_live_metrics(raw_path: Path) -> tuple[float | None, float | None]:
    """Best-effort live mean TTFT (ms) and decode TPS from raw.jsonl rows.

    raw.jsonl carries per-request proxy telemetry: timing fields in ms and
    provider-reported output tokens; local-token fields only exist after
    analysis, so live throughput uses provider output tokens.
    """
    ttft: list[float] = []
    decode_tps: list[float] = []
    if not raw_path.is_file():
        return None, None
    try:
        with raw_path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict) or row.get("event_type") != "inference":
                    continue
                timing = row.get("timing") or {}
                tokens = row.get("tokens") or {}
                first = timing.get("first_content_output_ms")
                last = timing.get("last_content_output_ms")
                end = timing.get("stream_completed_ms")
                tokens_row = tokens.get("output_provider")
                output_tokens = tokens_row.get("value") if isinstance(tokens_row, dict) else tokens_row
                if isinstance(first, (int, float)):
                    ttft.append(float(first))
                if not isinstance(output_tokens, (int, float)) or output_tokens <= 0:
                    continue
                decode_ms = None
                if isinstance(first, (int, float)) and isinstance(last, (int, float)) and float(last) >= float(first):
                    decode_ms = float(last) - float(first)
                if isinstance(end, (int, float)) and float(end) > 0:
                    decode_tps.append(float(output_tokens) / (float(end) / 1000.0))
                elif decode_ms and decode_ms > 0:
                    decode_tps.append(float(output_tokens) / (decode_ms / 1000.0))
    except OSError:
        return None, None
    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None
    return average(ttft), average(decode_tps)


def run_one(
    options: RunOptions,
    root_config: dict[str, Any] | None = None,
    progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    """Execute a benchmark run for one provider; returns the run directory.

    Preflight checks Docker, credentials, and provider access. Local tokenizer
    data is optional; missing data disables only local token metrics.

    ``progress`` is an optional callback receiving structured
    :class:`ProgressEvent` objects (silent when omitted). The harbor
    subprocess runs on the calling thread; a live UI therefore runs in a
    background thread and renders from the event stream plus the run
    directory named in the ``running`` event.

    ``cancel`` is an optional external cancellation event shared with the
    foreground: when set, owned Harbor/proxy children are terminated with
    bounded waits, the status becomes ``interrupted``, and
    ``KeyboardInterrupt`` propagates (never swallowed into success/failure).
    Cleanup touches only processes owned by this run's :class:`RunHandle`.
    """
    require_supported_execution_platform()
    emit = progress or _noop_progress
    started = time.monotonic()
    executable("docker")
    emit(_event("docker", "docker available"))
    root_config, config = provider_config(options.provider, root_config)
    spec = options.benchmark or benchmark_spec(root_config)
    context = resolve_tokenizer_context(root_config, spec, options.provider, options.benchmark_model)
    values = context["values"]
    endpoint, api_model = context["endpoint"], context["api_model"]
    model_settings = context["model_settings"]
    tokenizer = context["metadata"]
    emit(_event("tokenizer", "tokenizer cached" if tokenizer["source"] == "huggingface" else "tokenizer unavailable; provider token counts retained"))
    emit(_event("validate", f"validating {options.provider}"))
    result = validate_provider(options.provider, spec, root_config, config, values, api_model)
    if not result["success"]:
        raise SystemExit(f"provider validation failed: {result['error_class']}")
    tasks = task_names(options.mode, spec)
    emit(_event("validate", f"validated {options.provider} ({len(tasks)} tasks)", total=len(tasks)))
    handle = RunHandle(provider=options.provider, proxy_port=options.proxy_port, auth_token=new_proxy_token())
    if cancel is not None:
        handle.cancel_requested = cancel
    directory = run_directory(options, spec, config, endpoint, api_model, tasks, values, model_settings, proxy_auth_token=handle.auth_token)
    handle.directory = directory
    write_text_atomic(directory / "docker-host-gateway.yaml", "services:\n  main:\n    extra_hosts:\n      - host.docker.internal:host-gateway\n")
    command = harbor_command(options, spec, config, endpoint, api_model, directory, tasks, model_settings, proxy_auth_token=handle.auth_token)
    dump_json_atomic(directory / "command.json", redacted_command(command, handle.auth_token))
    env = environment(config, values)
    with track(handle):
        try:
            emit(_event("proxy", "starting telemetry proxy"))
            try:
                proxy = start_proxy(directory, options.proxy_port, handle.auth_token)
            except SystemExit:
                # Startup failure: Harbor never begins on an unverified proxy.
                _safe_set_status(directory, "failed", error="proxy failed to start")
                raise
            handle.register_proxy(proxy)
            if handle.cancelled:
                raise KeyboardInterrupt
            set_status(directory, "running", pid=None)
            emit(_event("running", f"running {len(tasks)} tasks at concurrency {options.concurrency}", total=len(tasks), run_dir=str(directory)))
            stdout_fh = (directory / "harbor.stdout.log").open("wb")
            stderr_fh = (directory / "harbor.stderr.log").open("wb")
            try:
                harbor = spawn_owned(command, cwd=None, env=env, stdout=stdout_fh, stderr=stderr_fh)
            finally:
                stdout_fh.close()
                stderr_fh.close()
            handle.register_harbor(harbor)
            write_text_atomic(directory / "pid", str(harbor.pid) + "\n")
            set_status(directory, "running", pid=harbor.pid)
            # wait_owned raises KeyboardInterrupt on cancellation and
            # SystemExit when the owned proxy dies mid-run; both paths
            # below terminate owned children with bounded waits.
            try:
                return_code = wait_owned(handle)
            except SystemExit:
                # Owned proxy died while Harbor was active: fail closed
                # instead of letting Harbor target a dead or foreign port.
                _safe_set_status(directory, "failed", pid=harbor.pid, error="owned proxy died during the run")
                raise
            if handle.cancelled:
                raise KeyboardInterrupt
            # Harbor finished: the proxy's job is done; stop it before analysis.
            handle.terminate_owned()
            if return_code != 0:
                set_status(directory, "failed", pid=harbor.pid, return_code=return_code)
                raise SystemExit(return_code)
            # Harbor exit 0 is NOT completion: canonical analysis and
            # publication must succeed first (C7).
            set_status(directory, "analyzing", pid=harbor.pid, return_code=return_code)
            emit(_event("analyze", "normalizing telemetry"))
            try:
                subprocess.run([sys.executable, "-m", "benching.analytics.analyze", str(directory)], cwd=None, check=True)
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                _safe_set_status(
                    directory, "failed", pid=harbor.pid, return_code=return_code,
                    phase="analysis", error=_short_error(exc),
                )
                raise
            try:
                verify_completion_artifacts(directory)
            except SystemExit as exc:
                _safe_set_status(
                    directory, "failed", pid=harbor.pid, return_code=return_code,
                    phase="publication", error=str(exc.code or exc),
                )
                raise
            set_status(directory, "completed", pid=harbor.pid, return_code=return_code)
            emit(_event("done", "run complete", elapsed_seconds=round(time.monotonic() - started, 1)))
            return directory
        except KeyboardInterrupt:
            # Cancellation during startup, active work, or shutdown:
            # terminate owned Harbor work first, then the proxy, record
            # interruption, and propagate without swallowing.
            handle.terminate_owned()
            _safe_set_status(directory, "interrupted")
            raise
        except BaseException:
            handle.terminate_owned()
            raise


def compare(
    providers: list[str],
    mode: str,
    model: str | None,
    concurrency: int,
    trials: int,
    root_config: dict[str, Any] | None = None,
    execution: str = "sequential",
    reasoning: str = "default",
) -> list[Path]:
    """Run one or more providers and analyze the combined run directories.

    Parallel runs share one cancellation event and use distinct proxy ports
    (``PROXY_PORT + index``) with distinct per-run auth tokens, so concurrent
    runs never share proxy identity, secrets, telemetry files, or ports.
    """
    root_config = root_config or load_yaml()
    directories: list[Path] = []
    if execution == "parallel":
        import concurrent.futures
        cancel = threading.Event()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="compare") as pool:
            futures = {
                pool.submit(run_one, RunOptions(provider=provider, mode=mode, benchmark_model=model, reasoning=reasoning, concurrency=concurrency, trials=trials, proxy_port=PROXY_PORT + index), root_config, None, cancel): index
                for index, provider in enumerate(providers)
            }
            try:
                for future in concurrent.futures.as_completed(futures):
                    directories.append(future.result())
            except BaseException:
                cancel.set()
                for future in futures:
                    future.cancel()
                raise
    else:
        for provider in providers:
            directories.append(run_one(RunOptions(provider=provider, mode=mode, benchmark_model=model, reasoning=reasoning, concurrency=concurrency, trials=trials), root_config))
    directories.sort(key=lambda d: d.name)
    return directories


def analyze_runs(directories: list[Path], execution: str = "sequential") -> None:
    """Normalize and compare the given run directories (benching.analytics.analyze)."""
    subprocess.run([sys.executable, "-m", "benching.analytics.analyze", "--execution", execution, *(str(path) for path in directories)], cwd=None, check=True)

