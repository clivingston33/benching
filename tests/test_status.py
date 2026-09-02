from __future__ import annotations

import json
from pathlib import Path

from benchmark.runner import RunProgress
from benchmark.status import ProgressEvent, scan_harbor_results


def _write_result(jobs_dir: Path, subdir: str, task: str, reward=None, exception=None) -> None:
    target = jobs_dir / subdir
    target.mkdir(parents=True, exist_ok=True)
    data: dict = {"task_name": f"terminal-bench/{task}", "verifier_result": {}, "exception_info": {}}
    if reward is not None:
        data["verifier_result"]["rewards"] = {"reward": reward}
    if exception is not None:
        data["exception_info"] = {"exception_type": exception}
    (target / "result.json").write_text(json.dumps(data), encoding="utf-8")


def test_scan_harbor_results_counts_outcomes(tmp_path: Path) -> None:
    jobs = tmp_path / "harbor"
    _write_result(jobs, "job-1", "task-a", reward=1.0)
    _write_result(jobs, "job-2", "task-b", reward=0.0)
    _write_result(jobs, "job-3", "task-c", exception="VerifierTimeoutError")
    _write_result(jobs, "job-4", "task-d", reward=None)
    results = scan_harbor_results(jobs)
    assert results["task-a"]["outcome"] == "passed"
    assert results["task-b"]["outcome"] == "failed"
    assert results["task-c"]["outcome"] == "timed_out"
    assert results["task-d"]["outcome"] == "failed"


def test_run_progress_refresh_aggregates(tmp_path: Path) -> None:
    jobs = tmp_path / "harbor"
    _write_result(jobs, "job-1", "task-a", reward=1.0)
    _write_result(jobs, "job-2", "task-b", reward=0.0)
    _write_result(jobs, "job-3", "task-c", exception="VerifierTimeoutError")
    progress = RunProgress(jobs_dir=jobs, total=5, raw_jsonl=None)
    snapshot = progress.refresh()
    assert snapshot["completed"] == 3
    assert snapshot["total"] == 5
    assert snapshot["passed"] == 1
    assert snapshot["failed"] == 2
    assert snapshot["running"] == 2


def test_progress_event_carries_structured_fields() -> None:
    event = ProgressEvent(phase="running", total=89, run_dir="/tmp/run", elapsed_seconds=12.5)
    assert event.total == 89
    assert event.run_dir == "/tmp/run"
    assert event.elapsed_seconds == 12.5
