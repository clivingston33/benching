from __future__ import annotations

import pytest

from analytics.analyze import compatible, distribution, local_count, local_tokenizer, normalize


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


def test_compatibility_allows_different_api_model_ids() -> None:
    common = {"benchmark": "task-suite", "benchmark_version": "1.0", "benchmark_model": "model-x", "reasoning_mode": "default", "streaming": True, "concurrency": 1, "trials": 1, "proxy_schema_version": 1, "tokenizer": {"repo": "org/tokenizer", "revision": "rev"}, "tasks": ["task-1"]}
    compatible([{**common, "provider": "acme", "api_model": "acme-model-1"}, {**common, "provider": "globex", "api_model": "globex-model-1"}])


def test_compatibility_rejects_different_canonical_models() -> None:
    common = {"benchmark": "task-suite", "benchmark_version": "1.0", "reasoning_mode": "default", "streaming": True, "concurrency": 1, "trials": 1, "proxy_schema_version": 1, "tokenizer": {"repo": "org/tokenizer", "revision": "rev"}, "tasks": ["task-1"]}
    with pytest.raises(SystemExit, match="benchmark_model"):
        compatible([{**common, "benchmark_model": "model-a", "provider": "acme"}, {**common, "benchmark_model": "model-b", "provider": "globex"}])


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
