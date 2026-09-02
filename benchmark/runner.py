"""Benchmark run execution: orchestrate Harbor runs behind the telemetry proxy."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark._paths import PROXY_PORT, ROOT, RUNS
from benchmark._util import utc
from benchmark.config import (
    BenchmarkSpec,
    benchmark_spec,
    env_path,
    environment,
    load_yaml,
    provider_config,
    provider_env_values,
    resolve,
)
from benchmark.status import ProgressEvent, ProgressFn, scan_harbor_results
from benchmark.tokenizer import tokenizer_metadata
from benchmark.validation import validate_provider

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
            raise SystemExit("smoke mode requires benchmark.smoke_tasks in config/benchmark.yaml")
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
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"required executable not found: {name}")
    return path


def version(name: str) -> str | None:
    path = shutil.which(name)
    if path is None:
        return None
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text[:256] or None


def fingerprint(run: dict[str, Any]) -> str:
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
) -> Path:
    """Create the isolated runs/<run-id>/ directory and its immutable run.json."""
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = f"{spec.run_id_prefix}-v1-{options.provider}-{options.mode}-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = RUNS / run_id
    directory.mkdir(parents=False)
    (directory / "harbor").mkdir()
    run = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": utc(),
        "benchmark": spec.name,
        "benchmark_version": spec.version,
        "benchmark_model": options.benchmark_model or spec.model,
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
        "os": platform.platform(),
        "kernel": platform.release(),
        "cpu": platform.processor(),
        "proxy_schema_version": 1,
        "proxy_port": options.proxy_port,
        "tokenizer": tokenizer_metadata(spec, env_values),
    }
    run["environment_fingerprint"] = fingerprint(run)
    (directory / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    routes = {options.provider: {"upstream": endpoint, "plan": config.get("plan"), "plan_tier": config.get("plan_tier", "unknown"), "reasoning": options.reasoning}}
    (directory / "proxy-routes.json").write_text(json.dumps(routes, indent=2) + "\n", encoding="utf-8")
    (directory / "status.json").write_text(json.dumps({"status": "created", "updated_at_utc": utc()}, indent=2) + "\n", encoding="utf-8")
    return directory


def harbor_command(options: RunOptions, spec: BenchmarkSpec, config: dict[str, Any], endpoint: str, api_model: str, directory: Path, tasks: list[str]) -> list[str]:
    """Build the Harbor run command that executes the suite in Docker."""
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
        "benchmark_model": options.benchmark_model or spec.model,
        "model": api_model,
        "upstream": endpoint,
        "api_key_env": config["auth_env"],
        "run_id": directory.name,
        "proxy_url": f"http://host.docker.internal:{options.proxy_port}",
        "api": config.get("api", "openai-completions"),
        "reasoning": options.reasoning,
        "max_tokens": str(spec.max_tokens),
        "context_window": str(spec.context_window),
    }
    for key, value in agent_kwargs.items():
        command.extend(["--agent-kwarg", f"{key}={value}"])
    for task in tasks:
        command.extend(["--include-task-name", task])
    return command


def start_proxy(directory: Path, port: int = PROXY_PORT) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-m", "proxy.telemetry_proxy", "--events", str(directory / "raw.jsonl"), "--routes", str(directory / "proxy-routes.json"), "--port", str(port)]
    stdout = (directory / "proxy.stdout.log").open("wb")
    stderr = (directory / "proxy.stderr.log").open("wb")
    process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)}, stdout=stdout, stderr=stderr, start_new_session=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                stdout.close(); stderr.close()
                return process
        except OSError:
            if process.poll() is not None:
                raise SystemExit(f"proxy failed to start; see {directory / 'proxy.stderr.log'}")
            time.sleep(0.1)
    stop_process(process)
    raise SystemExit("proxy did not become ready within 10 seconds")


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def set_status(directory: Path, status: str, **extra: Any) -> None:
    (directory / "status.json").write_text(json.dumps({"status": status, "updated_at_utc": utc(), **extra}, indent=2) + "\n", encoding="utf-8")


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
    average = lambda values: round(sum(values) / len(values), 1) if values else None
    return average(ttft), average(decode_tps)


def run_one(
    options: RunOptions,
    root_config: dict[str, Any] | None = None,
    progress: ProgressFn | None = None,
) -> Path:
    """Execute a benchmark run for one provider; returns the run directory.

    Preflight (docker, credentials, tokenizer cache, provider validation) is
    authoritative: any failure raises SystemExit before a run starts.

    ``progress`` is an optional callback receiving structured
    :class:`ProgressEvent` objects (silent when omitted). The harbor
    subprocess runs on the calling thread; a live UI therefore runs in a
    background thread and renders from the event stream plus the run
    directory named in the ``running`` event.
    """
    emit = progress or _noop_progress
    started = time.monotonic()
    executable("docker")
    emit(_event("docker", "docker available"))
    root_config, config = provider_config(options.provider, root_config)
    spec = options.benchmark or benchmark_spec(root_config)
    values = provider_env_values(options.provider, config)
    if options.reasoning != spec.reasoning:
        raise SystemExit(f"benchmark reasoning mode ({spec.reasoning}) does not match --reasoning {options.reasoning}")
    if options.benchmark_model and spec.model and options.benchmark_model != spec.model:
        raise SystemExit("--model does not match benchmark.model in config/benchmark.yaml")
    endpoint, api_model = resolve(options.provider, config, values)
    tokenizer = tokenizer_metadata(spec, values)
    if tokenizer["source"] != "huggingface":
        raise SystemExit("tokenizer is not cached; run `benching tokenizer prepare`")
    emit(_event("tokenizer", "tokenizer cached"))
    emit(_event("validate", f"validating {options.provider}"))
    result = validate_provider(options.provider, spec, root_config, config, values)
    if not result["success"]:
        raise SystemExit(f"provider validation failed: {result['error_class']}")
    tasks = task_names(options.mode, spec)
    emit(_event("validate", f"validated {options.provider} ({len(tasks)} tasks)", total=len(tasks)))
    directory = run_directory(options, spec, config, endpoint, api_model, tasks, values)
    (directory / "docker-host-gateway.yaml").write_text("services:\n  main:\n    extra_hosts:\n      - host.docker.internal:host-gateway\n", encoding="utf-8")
    command = harbor_command(options, spec, config, endpoint, api_model, directory, tasks)
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n", encoding="utf-8")
    env = environment(config, values)
    proxy: subprocess.Popen[bytes] | None = None
    try:
        emit(_event("proxy", "starting telemetry proxy"))
        proxy = start_proxy(directory, options.proxy_port)
        set_status(directory, "running", pid=None)
        emit(_event("running", f"running {len(tasks)} tasks at concurrency {options.concurrency}", total=len(tasks), run_dir=str(directory)))
        with (directory / "harbor.stdout.log").open("wb") as stdout, (directory / "harbor.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        (directory / "pid").write_text(str(process.pid) + "\n", encoding="utf-8")
        set_status(directory, "running", pid=process.pid)
        return_code = process.wait()
        set_status(directory, "completed" if return_code == 0 else "failed", pid=process.pid, return_code=return_code)
        if return_code != 0:
            raise SystemExit(return_code)
        emit(_event("analyze", "normalizing telemetry"))
        subprocess.run([sys.executable, str(ROOT / "analytics" / "analyze.py"), str(directory)], cwd=ROOT, check=True)
        emit(_event("done", "run complete", elapsed_seconds=round(time.monotonic() - started, 1)))
        return directory
    except KeyboardInterrupt:
        set_status(directory, "interrupted")
        raise
    finally:
        stop_process(proxy)


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
    """Run one or more providers and analyze the combined run directories."""
    root_config = root_config or load_yaml()
    directories: list[Path] = []
    if execution == "parallel":
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers), thread_name_prefix="compare") as pool:
            futures = {
                pool.submit(run_one, RunOptions(provider=provider, mode=mode, benchmark_model=model, reasoning=reasoning, concurrency=concurrency, trials=trials, proxy_port=PROXY_PORT + index), root_config): index
                for index, provider in enumerate(providers)
            }
            for future in concurrent.futures.as_completed(futures):
                directories.append(future.result())
    else:
        for provider in providers:
            directories.append(run_one(RunOptions(provider=provider, mode=mode, benchmark_model=model, reasoning=reasoning, concurrency=concurrency, trials=trials), root_config))
    directories.sort(key=lambda d: d.name)
    return directories


def analyze_runs(directories: list[Path], execution: str = "sequential") -> None:
    """Normalize and compare the given run directories (analytics/analyze.py)."""
    subprocess.run([sys.executable, str(ROOT / "analytics" / "analyze.py"), "--execution", execution, *(str(path) for path in directories)], cwd=ROOT, check=True)
