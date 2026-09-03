"""Synthetic benchmark run for UI development without live infrastructure.

Emits the same structured :class:`ProgressEvent` stream that a real run
produces (preflight phases, then per-task lifecycle), and writes fake
harbor per-task result.json files plus raw.jsonl rows so the real CLI
render path — including harbor-result polling and live metric tails — can
be exercised end to end with no Docker, provider keys, or harbor binary.

Designed to be consumed by the same ``cli.live`` view driver as
``benching run``, so the TUI/dashboard can be developed against it too.
"""
from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark._paths import RUNS
from benchmark.status import ProgressEvent

# Task names sampled for the fake suite (recognizable terminal-agent tasks).
_DEMO_TASKS = [
    "break-filter-js-from-html",
    "cancel-async-tasks",
    "adaptive-rejection-sampler",
    "refactor-class-to-functions",
    "fix-css-overflow-bug",
    "optimize-sql-query",
    "write-pytest-suite",
    "debug-api-timeout",
    "migrate-config-format",
    "implement-retry-logic",
]


class DemoRun:
    """Builds a fake run directory and replays a scripted event stream."""

    def __init__(
        self,
        provider: str = "acme",
        total: int = 10,
        failure_rate: float = 0.2,
        task_seconds: float = 0.4,
        seed: int = 1,
    ) -> None:
        self.provider = provider
        self.total = total
        self.failure_rate = failure_rate
        self.task_seconds = task_seconds
        self.rng = random.Random(seed)
        self.started_mono: float | None = None
        self.completed = 0
        self.passed = 0
        self.failed = 0
        # Fake run directory under runs/demo-* (cleaned by caller or left as a
        # reproducible artifact for runs/results views).
        self.directory: Path | None = None
        self.tasks = [f"task-{index:02d}" for index in range(total)]

    # -- run directory -------------------------------------------------------
    def create_directory(self) -> Path:
        run_id = f"demo-v1-{self.provider}-full-{datetime.now(UTC):%Y%m%d-%H%M%S}-{self.rng.randrange(16**8):08x}"
        directory = RUNS / run_id
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "harbor").mkdir()
        run = {
            "schema_version": 1,
            "run_id": run_id,
            "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "benchmark": "demo-suite",
            "benchmark_version": "1.0",
            "benchmark_model": "demo-model-1",
            "task_count": self.total,
            "tasks": self.tasks,
            "agent": "agents.instrumented_omp_agent:InstrumentedOmpAgent",
            "provider": self.provider,
            "provider_plan": None,
            "provider_plan_tier": "unknown",
            "endpoint": "https://demo.invalid/v1",
            "api_model": "demo-model-1",
            "reasoning_mode": "default",
            "streaming": True,
            "concurrency": 3,
            "trials": 1,
            "proxy_schema_version": 1,
            "proxy_port": 8765,
            "tokenizer": {"repo": "demo/tokenizer", "revision": "demo", "source": "huggingface", "local_cache": "/nonexistent"},
        }
        (directory / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
        (directory / "status.json").write_text(json.dumps({"status": "created", "updated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z")}, indent=2) + "\n", encoding="utf-8")
        (directory / "raw.jsonl").touch()
        self.directory = directory
        return directory

    # -- event stream --------------------------------------------------------
    def events(self):
        """Generator yielding ProgressEvent objects over the fake run."""
        if self.directory is None:
            self.create_directory()
        assert self.directory is not None
        self.started_mono = time.monotonic()
        yield ProgressEvent(phase="docker", message="docker available")
        yield ProgressEvent(phase="tokenizer", message="tokenizer cached")
        yield ProgressEvent(phase="validate", message=f"validating {self.provider}")
        yield ProgressEvent(phase="validate", message=f"validated {self.provider} ({self.total} tasks)", total=self.total)
        yield ProgressEvent(phase="proxy", message="starting telemetry proxy")
        yield ProgressEvent(
            phase="running",
            message=f"running {self.total} tasks at concurrency 3",
            total=self.total,
            run_dir=str(self.directory),
        )
        for task in self.tasks:
            # task_started
            yield ProgressEvent(phase="task_started", message=f"started {task}", task_id=task, total=self.total)
            time.sleep(self.task_seconds)
            # Simulate live raw.jsonl telemetry rows as the task produces them.
            self._append_raw(task)
            passed = self.rng.random() >= self.failure_rate
            self.completed += 1
            if passed:
                self.passed += 1
                outcome = "task_completed"
            else:
                self.failed += 1
                outcome = self._maybe_timeout(task)
            self._write_result(task, passed)
            elapsed = time.monotonic() - (self.started_mono or time.monotonic())
            yield ProgressEvent(
                phase=outcome,
                message=f"{task} {'passed' if passed else 'failed'}",
                task_id=task,
                completed=self.completed,
                passed=self.passed,
                failed=self.failed,
                running=max(0, self.total - self.completed),
                total=self.total,
                elapsed_seconds=round(elapsed, 1),
            )
        yield ProgressEvent(phase="done", message="run complete", total=self.total, completed=self.total, passed=self.passed, failed=self.failed, running=0, elapsed_seconds=round(time.monotonic() - (self.started_mono or time.monotonic()), 1))
        # Final status
        status = {"status": "completed", "updated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
        (self.directory / "status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    def _maybe_timeout(self, task: str) -> str:
        return "task_timed_out" if self.rng.random() < 0.3 else "task_failed"

    # -- fake artifacts ------------------------------------------------------
    def _result_dir(self, task: str) -> Path:
        assert self.directory is not None
        target = self.directory / "harbor" / f"job-{task}"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _write_result(self, task: str, passed: bool) -> None:
        data: dict[str, Any] = {"task_name": f"terminal-bench/{task}", "verifier_result": {"rewards": {"reward": 1.0 if passed else 0.0}}, "exception_info": {}}
        if not passed and self.rng.random() < 0.3:
            data["exception_info"] = {"exception_type": "VerifierTimeoutError"}
        (self._result_dir(task) / "result.json").write_text(json.dumps(data), encoding="utf-8")

    def _append_raw(self, task: str) -> None:
        assert self.directory is not None
        row = {
            "schema_version": 1,
            "event_type": "inference",
            "request_id": f"demo-{task}",
            "provider": self.provider,
            "task_id": task,
            "trial_id": "t1",
            "model": "demo-model-1",
            "timing": {
                "first_content_output_ms": 150.0 + self.rng.uniform(0, 600),
                "last_content_output_ms": 800.0 + self.rng.uniform(0, 900),
                "stream_completed_ms": 1200.0 + self.rng.uniform(0, 800),
            },
            "tokens": {"input_provider": int(400 + self.rng.uniform(0, 900)), "output_provider": int(50 + self.rng.uniform(0, 200)), "total_provider": 0, "cache_read": 0, "cache_write": 0},
            "output_text": "demo output",
            "output_text_truncated": False,
            "success": True,
            "stream_completed": True,
            "http_status": 200,
        }
        with (self.directory / "raw.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
