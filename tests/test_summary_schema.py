from __future__ import annotations

import json
from pathlib import Path

from benching.analytics.analyze import normalize_runs

FIXTURE = Path(__file__).parent / "fixtures" / "summary.json"
SUMMARY_KEYS = {
    "schema_version",
    "run_id",
    "created_at_utc",
    "benchmark",
    "provider",
    "model",
    "reasoning",
    "execution",
    "score",
    "speed",
    "latency",
    "reliability",
    "tokens",
    "context",
    "tasks",
}


def summary_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def assert_summary_schema(summary: dict) -> None:
    assert set(summary) == SUMMARY_KEYS
    assert summary["schema_version"] == 1
    assert set(summary["benchmark"]) == {"name", "version", "task_count"}
    assert set(summary["provider"]) == {"id", "name"}
    assert isinstance(summary["model"], str)
    assert summary["reasoning"] in {"default", "enabled", "disabled"}
    assert set(summary["execution"]) == {"concurrency", "trials"}
    assert {"passed", "failed", "total", "success_rate"} <= set(summary["score"])
    assert {"successful_requests", "failed_requests", "success_rate"} <= set(summary["reliability"])
    assert {"input", "output", "cache_read"} <= set(summary["tokens"])
    assert set(summary["context"]) == {"0-4K", "4K-16K", "16K-32K", "32K-64K", "64K+"}
    assert isinstance(summary["tasks"], list)
    if summary["tasks"]:
        assert {
            "task_id", "trial_id", "passed", "reward", "duration_sec", "exception",
            "timeout", "requests", "tokens", "latency", "reliability",
        } == set(summary["tasks"][0])


def write_run(root: Path, index: int, model: str, tokenizer: tuple[str | None, str | None], *, success: bool = True, timeout: bool = False) -> Path:
    directory = root / f"run-{index}"
    directory.mkdir()
    (directory / "harbor").mkdir()
    run = {
        "run_id": directory.name,
        "benchmark": "terminal-bench",
        "benchmark_version": "2.1",
        "task_count": 1,
        "tasks": ["task-1"],
        "provider": f"provider-{index}",
        "model": model,
        "api_model": model,
        "reasoning_mode": "default",
        "concurrency": 3,
        "trials": 1,
        "streaming": True,
        "proxy_schema_version": 1,
        "tokenizer": {"repo": tokenizer[0], "revision": tokenizer[1], "local_cache": str(root / f"missing-{index}")},
    }
    row = {
        "event_type": "inference",
        "run_id": directory.name,
        "request_id": f"request-{index}",
        "provider": run["provider"],
        "task_id": "task-1",
        "trial_id": "trial-1",
        "model": model,
        "timing": {"first_content_output_ms": 100.0, "last_content_output_ms": 600.0, "stream_completed_ms": 900.0},
        "tokens": {"input_provider": 100, "output_provider": 50, "total_provider": 150, "cache_read": None, "cache_write": None},
        "output_text": "hello",
        "output_text_truncated": False,
        "success": success,
        "stream_completed": success,
        "downstream_cancelled": False,
        "provider_failure": not success,
        "error_type": "TimeoutError" if timeout else None,
        "http_status": 200 if success else 504,
    }
    (directory / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (directory / "raw.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return directory


def write_harbor_result(directory: Path, task_id: str, trial_id: str, *, reward: float | None = None, exception: str | None = None, duration_sec: float | None = 12.5) -> None:
    result = {
        "task_name": f"terminal-bench/{task_id}",
        "trial_id": trial_id,
        "duration_sec": duration_sec,
        "verifier_result": {},
        "exception_info": {},
    }
    if reward is not None:
        result["verifier_result"] = {"rewards": {"reward": reward}}
    if exception is not None:
        result["exception_info"] = {"exception_type": exception}
    target = directory / "harbor" / f"{task_id}-{trial_id}"
    target.mkdir(parents=True)
    (target / "result.json").write_text(json.dumps(result), encoding="utf-8")


def task_run(tmp_path: Path, outcomes: list[tuple[str, str, float | None, str | None, int]]) -> dict:
    directory = write_run(tmp_path, 1, "model-a", ("org/tokenizer", "rev"))
    # Planned tasks must match observed outcomes: real runs only ever
    # observe their planned tasks, and planned-but-unobserved tasks now
    # correctly surface as explicit missing entries.
    planned = sorted({task_id for task_id, _, _, _, _ in outcomes})
    run_path = directory / "run.json"
    run_doc = json.loads(run_path.read_text(encoding="utf-8"))
    run_doc["tasks"] = planned
    run_path.write_text(json.dumps(run_doc), encoding="utf-8")
    rows = []
    for task_id, trial_id, reward, exception, request_count in outcomes:
        for request_index in range(request_count):
            rows.append(
                {
                    "event_type": "inference",
                    "run_id": directory.name,
                    "request_id": f"{task_id}-{trial_id}-{request_index}",
                    "provider": "provider-1",
                    "task_id": task_id,
                    "trial_id": trial_id,
                    "model": "model-a",
                    "timing": {"first_content_output_ms": 100.0, "last_content_output_ms": 600.0, "stream_completed_ms": 900.0},
                    "tokens": {"input_provider": 100, "output_provider": 50, "total_provider": 150, "cache_read": 25, "cache_write": None},
                    "output_text": "hello",
                    "output_text_truncated": False,
                    "success": exception is None,
                    "stream_completed": exception is None,
                    "downstream_cancelled": False,
                    "provider_failure": exception is not None,
                    "error_type": exception,
                    "http_status": 200 if exception is None else 504,
                }
            )
        write_harbor_result(directory, task_id, trial_id, reward=reward, exception=exception)
    (directory / "raw.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return normalize_runs([directory], write_comparison=False)["runs"][0]


def comparison(tmp_path: Path, models: tuple[str, str], tokenizers: tuple[tuple[str | None, str | None], tuple[str | None, str | None]]) -> dict:
    directories = [write_run(tmp_path, index, model, tokenizers[index]) for index, model in enumerate(models)]
    return normalize_runs(directories, write_comparison=False)


def test_single_provider_summary() -> None:
    summary = summary_fixture()
    assert_summary_schema(summary)
    assert summary["provider"] == {"id": "fireworks", "name": "Fireworks"}


def test_two_providers_same_model_comparison(tmp_path: Path) -> None:
    result = comparison(tmp_path, ("model-a", "model-a"), (("org/tokenizer", "rev"), ("org/tokenizer", "rev")))
    assert result["models"] == ["model-a"]
    assert len(result["runs"]) == 2


def test_two_providers_different_models_comparison(tmp_path: Path) -> None:
    result = comparison(tmp_path, ("model-a", "model-b"), (("org/tokenizer", "rev"), ("org/tokenizer", "rev")))
    assert result["models"] == ["model-a", "model-b"]


def test_same_tokenizer_is_comparable(tmp_path: Path) -> None:
    assert comparison(tmp_path, ("model-a", "model-b"), (("org/tokenizer", "rev"), ("org/tokenizer", "rev")))["tokenizers_comparable"] is True


def test_different_tokenizer_is_not_locally_comparable(tmp_path: Path) -> None:
    result = comparison(tmp_path, ("model-a", "model-b"), (("org/claude", "rev-a"), ("org/deepseek", "rev-b")))
    assert result["tokenizers_comparable"] is False
    assert all(run["tokens"]["output_local"] is None for run in result["runs"])


def test_missing_local_tokenizer_preserves_provider_tokens() -> None:
    summary = summary_fixture()
    assert summary["tokens"]["output_local"] is None
    assert summary["tokens"]["output"] == 3190000
    assert summary["speed"]["output_tps_mean"] == 72.4


def test_failed_requests_are_represented_in_summary() -> None:
    summary = summary_fixture()
    assert summary["reliability"]["failed_requests"] == 7
    assert summary["reliability"]["successful_requests"] == 1234
    assert summary["reliability"]["success_rate"] < 1


def test_task_timeout_is_represented_in_summary() -> None:
    summary = summary_fixture()
    timeout_tasks = [task for task in summary["tasks"] if task["timeout"]]
    assert timeout_tasks
    assert summary["score"]["timeout"] == 1


def test_smoke_run_summary() -> None:
    summary = summary_fixture()
    summary["run_id"] = summary["run_id"].replace("full", "smoke")
    summary["benchmark"]["task_count"] = 3
    assert_summary_schema(summary)
    assert summary["benchmark"]["task_count"] == 3


def test_full_run_summary() -> None:
    summary = summary_fixture()
    assert_summary_schema(summary)
    assert summary["run_id"].endswith("ab12cd34")
    assert summary["benchmark"]["task_count"] == 89


def test_passed_task_uses_harbor_outcome(tmp_path: Path) -> None:
    summary = task_run(tmp_path, [("task-pass", "trial-1", 1.0, None, 1)])
    task = summary["tasks"][0]
    assert task["passed"] is True
    assert task["reward"] == 1.0
    assert task["exception"] is None


def test_failed_verifier_task_uses_harbor_reward(tmp_path: Path) -> None:
    task = task_run(tmp_path, [("task-fail", "trial-1", 0.0, None, 1)])["tasks"][0]
    assert task["passed"] is False
    assert task["reward"] == 0.0

    assert task["timeout"] is False
def test_timed_out_task_preserves_missing_reward(tmp_path: Path) -> None:
    task = task_run(tmp_path, [("task-timeout", "trial-1", None, "VerifierTimeoutError", 0)])["tasks"][0]
    assert task["passed"] is None
    assert task["reward"] is None
    assert task["timeout"] is True
    assert task["requests"] == 0


def test_errored_task_preserves_exception(tmp_path: Path) -> None:
    task = task_run(tmp_path, [("task-error", "trial-1", None, "ContainerError", 1)])["tasks"][0]
    assert task["passed"] is None
    assert task["exception"] == "ContainerError"
    assert task["timeout"] is False


def test_multiple_requests_produce_one_task_entry(tmp_path: Path) -> None:
    summary = task_run(tmp_path, [("task-many", "trial-1", 1.0, None, 3)])
    assert len(summary["tasks"]) == 1
    assert summary["tasks"][0]["requests"] == 3
    assert len(summary["tasks"]) != 3
    assert summary["tasks"][0]["tokens"]["input"] == 300


def test_multiple_trials_produce_one_entry_per_trial(tmp_path: Path) -> None:
    summary = task_run(
        tmp_path,
        [
            ("task-trials", "trial-1", 1.0, None, 1),
            ("task-trials", "trial-2", 0.0, None, 2),
        ],
    )
    assert {(task["task_id"], task["trial_id"]) for task in summary["tasks"]} == {
        ("task-trials", "trial-1"),
        ("task-trials", "trial-2"),
    }
    assert [task["requests"] for task in summary["tasks"]] == [1, 2]


def test_context_buckets_are_canonical_and_normalized(tmp_path: Path) -> None:
    summary = task_run(tmp_path, [("task-context", "trial-1", 1.0, None, 2)])
    bucket = summary["context"]["0-4K"]
    assert bucket["requests"] == 2
    assert bucket["ttft_ms"]["mean"] == 100.0
    assert bucket["decode_tps"]["p50"] is None
    assert bucket["failure_rate"] == 0.0

