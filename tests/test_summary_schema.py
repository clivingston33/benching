from __future__ import annotations

import json
from pathlib import Path

from analytics.analyze import normalize_runs

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
    assert isinstance(summary["tasks"], list)


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
    timeout_tasks = [task for task in summary["tasks"] if task["reliability"].get("timeout")]
    assert timeout_tasks
    assert summary["score"]["timeout"] == 0


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
