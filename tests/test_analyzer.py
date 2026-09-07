from __future__ import annotations

import json
import pytest
from analytics.analyze import compatible, distribution, local_count, local_tokenizer, normalize, normalize_runs


class FakeEncoding:
    ids = [1, 2, 3, 4, 5]


class FakeTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> FakeEncoding:
        return FakeEncoding()


def raw_row() -> dict:
    return {
        "event_type": "inference",
        "run_id": "run-1",
        "request_id": "req-1",
        "provider": "acme",
        "task_id": "task-1",
        "trial_id": "trial-1",
        "model": "acme-model-1",
        "timing": {"first_content_output_ms": 100.0, "last_content_output_ms": 600.0, "stream_completed_ms": 900.0},
        "tokens": {"input_provider": 100, "output_provider": 50, "total_provider": 150, "cache_read": None, "cache_write": None},
        "output_text": "hello",
        "output_text_truncated": False,
        "success": True,
        "stream_completed": True,
        "http_status": 200,
    }


def test_normalize_keeps_canonical_and_api_models() -> None:
    run = {"run_id": "run-1", "provider": "acme", "benchmark_model": "model-x", "api_model": "acme-model-1"}
    row = normalize(run, [raw_row()], FakeTokenizer())[0]
    assert row["benchmark_model"] == "model-x"
    assert row["api_model"] == "acme-model-1"
    assert row["task_id"] == "task-1"
    assert row["trial_id"] == "trial-1"
    assert row["timing"]["decode_duration_ms"]["value"] == 500.0
    assert row["timing"]["decode_tps"]["value"] == 10.0
    assert row["timing"]["effective_tps"]["value"] == 5.555556


def test_truncated_output_makes_local_metrics_unavailable() -> None:
    row = raw_row()
    row["output_text_truncated"] = True
    normalized = normalize({"run_id": "run-1", "provider": "acme", "benchmark_model": "model-x", "api_model": "acme-model-1"}, [row], FakeTokenizer())[0]
    assert normalized["tokens"]["output_local"] == {"value": None, "source": "unavailable"}
    assert normalized["timing"]["decode_tps"] == {"value": None, "source": "unavailable"}


def test_compatibility_allows_different_selected_models() -> None:
    common = {"benchmark": "task-suite", "benchmark_version": "1.0", "reasoning_mode": "default", "streaming": True, "concurrency": 1, "trials": 1, "proxy_schema_version": 1, "tokenizer": {"repo": None, "revision": None}, "tasks": ["task-1"]}
    compatible([{**common, "model": "model-a", "provider": "acme"}, {**common, "model": "model-b", "provider": "globex"}])


def test_normalize_allows_different_tokenizers_without_local_metrics(tmp_path) -> None:
    directories = []
    for index, tokenizer in enumerate((("org/claude", "rev-a"), ("org/deepseek", "rev-b"))):
        directory = tmp_path / f"run-{index}"
        directory.mkdir()
        (directory / "harbor").mkdir()
        run = {
            "run_id": f"run-{index}",
            "benchmark": "task-suite",
            "benchmark_version": "1.0",
            "reasoning_mode": "default",
            "streaming": True,
            "concurrency": 1,
            "trials": 1,
            "proxy_schema_version": 1,
            "tasks": ["task-1"],
            "model": f"model-{index}",
            "api_model": f"model-{index}",
            "tokenizer": {"repo": tokenizer[0], "revision": tokenizer[1], "local_cache": str(tmp_path / f"missing-{index}")},
        }
        (directory / "run.json").write_text(json.dumps(run), encoding="utf-8")
        (directory / "raw.jsonl").write_text(json.dumps(raw_row()) + "\n", encoding="utf-8")
        directories.append(directory)
    comparison = normalize_runs(directories, write_comparison=False)
    assert comparison["models"] == ["model-0", "model-1"]
    assert comparison["tokenizers_comparable"] is False
    for directory in directories:
        row = json.loads((directory / "metrics.jsonl").read_text().splitlines()[0])
        assert row["timing"]["ttft_ms"]["value"] == 100.0
        assert row["tokens"]["output_provider"] == {"value": 50, "source": "reported"}
        assert row["tokens"]["output_local"] == {"value": None, "source": "unavailable"}


def test_compatibility_rejects_different_concurrency() -> None:
    common = {"benchmark": "task-suite", "benchmark_version": "1.0", "reasoning_mode": "default", "streaming": True, "trials": 1, "proxy_schema_version": 1, "tokenizer": {"repo": None, "revision": None}, "tasks": ["task-1"]}
    with pytest.raises(SystemExit, match="incompatible runs: concurrency"):
        compatible([{**common, "concurrency": 1}, {**common, "concurrency": 3}])


def test_local_tokenizer_override_counts_exact_tokens(tmp_path) -> None:
    from tokenizers import Tokenizer, models
    path = tmp_path / "tokenizer.json"
    Tokenizer(models.WordLevel({"hello": 0, "[UNK]": 1}, unk_token="[UNK]")).save(str(path))
    tokenizer = local_tokenizer(str(path))
    assert tokenizer is not None
    assert local_count(tokenizer, "hello", False) == 1


def test_missing_local_tokenizer_is_unavailable(tmp_path) -> None:
    assert local_tokenizer(str(tmp_path / "missing-tokenizer.json")) is None


def test_distribution_reports_percentiles_and_cv() -> None:
    result = distribution([1.0, 2.0, 3.0, 4.0])
    assert result["count"] == 4
    assert result["median"] == 2.5
    assert result["p95"] == 3.85
    assert result["cv"] is not None


def test_downstream_cancel_is_not_provider_failure() -> None:
    row = raw_row()
    row.update({"stream_completed": False, "downstream_cancelled": True, "provider_failure": False, "error_type": "downstream_disconnect"})
    normalized = normalize({"run_id": "run-1", "provider": "acme", "benchmark_model": "model-x", "api_model": "acme-model-1"}, [row], None)[0]
    reliability = normalized["reliability"]
    assert reliability["downstream_cancelled"] is True
    assert reliability["provider_failure"] is False
    assert reliability["provider_stream_failure"] is False
    assert reliability["incomplete_provider_stream"] is False

def test_normalize_writes_canonical_dashboard_summary_with_unavailable_local_metrics(tmp_path) -> None:
    directory = tmp_path / "run-1"
    directory.mkdir()
    (directory / "harbor" / "eval").mkdir(parents=True)
    run = {
        "schema_version": 1,
        "run_id": "run-1",
        "created_at_utc": "2026-01-02T03:04:05Z",
        "benchmark": "task-suite",
        "benchmark_version": "1.0",
        "task_count": 1,
        "tasks": ["task-1"],
        "provider": "acme",
        "model": "api-model-1",
        "benchmark_model": "model-x",
        "api_model": "api-model-1",
        "reasoning_mode": "enabled",
        "concurrency": 3,
        "trials": 2,
        "tokenizer": {"repo": "org/tokenizer", "revision": "rev-1", "local_cache": str(tmp_path / "missing-tokenizer")},
    }
    (directory / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (directory / "raw.jsonl").write_text(json.dumps(raw_row()) + "\n", encoding="utf-8")
    (directory / "harbor" / "eval" / "result.json").write_text(
        json.dumps({
            "n_total_trials": 1,
            "stats": {
                "n_completed_trials": 1,
                "n_errored_trials": 0,
                "evals": {"task-suite": {"reward_stats": {"reward": {"1.0": ["task-1"]}}}},
            },
        }),
        encoding="utf-8",
    )

    comparison = normalize_runs([directory], write_comparison=False)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))

    assert comparison["models"] == ["api-model-1"]
    assert set(summary) == {
        "schema_version", "run_id", "created_at_utc", "benchmark", "provider",
        "model", "reasoning", "execution", "score", "speed", "latency",
        "reliability", "tokens", "tasks",
    }
    assert summary["schema_version"] == 1
    assert summary["run_id"] == "run-1"
    assert summary["created_at_utc"] == "2026-01-02T03:04:05Z"
    assert summary["benchmark"] == {"name": "task-suite", "version": "1.0", "task_count": 1}
    assert summary["provider"] == {"id": "acme", "name": "acme"}
    assert summary["model"] == "api-model-1"
    assert summary["reasoning"] == "enabled"
    assert summary["execution"] == {"concurrency": 3, "trials": 2}
    assert summary["score"]["value"] == 1.0
    assert summary["score"]["passed"] == 1
    assert summary["score"]["total"] == 1
    assert summary["reliability"]["request_success_rate"] == 1.0
    assert summary["reliability"]["stream_completion_rate"] == 1.0
    assert summary["tokens"]["total_provider"] == 150
    assert summary["tokens"]["output_local"] is None
    assert summary["speed"]["decode_tps"]["mean"] is None
    assert summary["speed"]["effective_tps"]["mean"] is None
    assert summary["tasks"][0]["task_id"] == "task-1"
