from __future__ import annotations

import pytest

from analytics.analyze import compatible, distribution, normalize


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
        "provider": "kourier",
        "task_id": "task-1",
        "trial_id": "trial-1",
        "model": "DSV4-Flash-0731",
        "timing": {"first_content_output_ms": 100.0, "last_content_output_ms": 600.0, "stream_completed_ms": 900.0},
        "tokens": {"input_provider": 100, "output_provider": 50, "total_provider": 150, "cache_read": None, "cache_write": None},
        "output_text": "hello",
        "output_text_truncated": False,
        "success": True,
        "stream_completed": True,
        "http_status": 200,
    }


def test_normalize_keeps_canonical_and_api_models() -> None:
    run = {"run_id": "run-1", "provider": "kourier", "benchmark_model": "deepseek-v4-flash-0731", "api_model": "DSV4-Flash-0731"}
    row = normalize(run, [raw_row()], FakeTokenizer())[0]
    assert row["benchmark_model"] == "deepseek-v4-flash-0731"
    assert row["api_model"] == "DSV4-Flash-0731"
    assert row["task_id"] == "task-1"
    assert row["trial_id"] == "trial-1"
    assert row["timing"]["decode_duration_ms"]["value"] == 500.0
    assert row["timing"]["decode_tps"]["value"] == 10.0
    assert row["timing"]["effective_tps"]["value"] == 5.555556


def test_truncated_output_makes_local_metrics_unavailable() -> None:
    row = raw_row()
    row["output_text_truncated"] = True
    normalized = normalize({"run_id": "run-1", "provider": "kourier", "benchmark_model": "deepseek-v4-flash-0731", "api_model": "DSV4-Flash-0731"}, [row], FakeTokenizer())[0]
    assert normalized["tokens"]["output_local"] == {"value": None, "source": "unavailable"}
    assert normalized["timing"]["decode_tps"] == {"value": None, "source": "unavailable"}


def test_compatibility_allows_different_api_model_ids() -> None:
    common = {"benchmark": "terminal-bench", "benchmark_version": "2.1", "benchmark_model": "deepseek-v4-flash-0731", "reasoning": False, "streaming": True, "concurrency": 1, "trials": 1, "proxy_schema_version": 1, "tokenizer_path": None, "tasks": ["task-1"]}
    compatible([{**common, "provider": "kourier", "api_model": "DSV4-Flash-0731"}, {**common, "provider": "electronhub", "api_model": "deepseek-v4-flash-0731:dev"}])


def test_compatibility_rejects_different_canonical_models() -> None:
    common = {"benchmark": "terminal-bench", "benchmark_version": "2.1", "reasoning": False, "streaming": True, "concurrency": 1, "trials": 1, "proxy_schema_version": 1, "tokenizer_path": None, "tasks": ["task-1"]}
    with pytest.raises(SystemExit, match="benchmark_model"):
        compatible([{**common, "benchmark_model": "model-a", "provider": "kourier"}, {**common, "benchmark_model": "model-b", "provider": "electronhub"}])


def test_distribution_reports_percentiles_and_cv() -> None:
    result = distribution([1.0, 2.0, 3.0, 4.0])
    assert result["count"] == 4
    assert result["median"] == 2.5
    assert result["p95"] == 3.85
    assert result["cv"] is not None
