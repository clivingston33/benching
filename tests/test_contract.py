"""M2-task-7 contract tests: schemas, invariants, fixtures, sync.

Producer side of the cross-repo contract gate. Dashboard-side checks live
in benching-dashboard/tests. Shared corpora stay byte-identical while both
repos are checked out together; sync assertions skip otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "artifacts"
DASHBOARD = Path(__file__).resolve().parents[1].parent / "benching-dashboard"

VOCAB = {f"w{i}": i for i in range(100)}
VOCAB["[UNK]"] = 100


def _synthetic_evidence(root: Path, name: str, model: str, words: int) -> Path:
    """Recreate the examples/artifacts evidence deterministically."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    directory = root / name
    (directory / "harbor").mkdir(parents=True)
    tokenizer = Tokenizer(models.WordLevel(VOCAB, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tok_path = root / f"{name}-tok.json"
    tokenizer.save(str(tok_path))
    text = " ".join(f"w{i}" for i in range(words))
    run = {
        "run_id": name,
        "created_at_utc": "2026-09-08T00:00:00Z",
        "benchmark": "terminal-bench",
        "benchmark_version": "2.1",
        "task_count": 2,
        "tasks": ["task-a", "task-b"],
        "provider": "fireworks",
        "provider_name": "Fireworks",
        "model": model,
        "api_model": model,
        "reasoning_mode": "default",
        "concurrency": 1,
        "trials": 1,
        "streaming": True,
        "proxy_schema_version": 1,
        "tokenizer": {"repo": "org/example-tok", "revision": "rev-1", "local_cache": str(tok_path)},
    }
    (directory / "run.json").write_text(json.dumps(run), encoding="utf-8")
    rows = []
    for index, task in enumerate(("task-a", "task-b")):
        rows.append({
            "event_type": "inference",
            "run_id": name,
            "request_id": f"{name}-req-{index}",
            "provider": "fireworks",
            "task_id": task,
            "trial_id": "trial-0",
            "model": model,
            "timing": {"first_content_output_ms": 0.0, "last_content_output_ms": 1000.0, "stream_completed_ms": 2000.0},
            "tokens": {"input_provider": 50, "output_provider": words, "total_provider": 50 + words, "cache_read": None, "cache_write": None},
            "output_text": text,
            "output_text_truncated": False,
            "success": True,
            "stream_completed": True,
            "http_status": 200,
        })
        target = directory / "harbor" / task
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_text(json.dumps({
            "task_name": f"terminal-bench/{task}",
            "trial_id": "trial-0",
            "verifier_result": {"rewards": {"reward": 1.0}},
            "exception_info": {},
        }), encoding="utf-8")
    (directory / "raw.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return directory


def test_schemas_are_valid_draft_2020_12_with_stable_ids() -> None:
    from benching.benchmark.contract import COMPARISON_SCHEMA, SUMMARY_SCHEMA, load_schema

    summary = load_schema(SUMMARY_SCHEMA)
    comparison = load_schema(COMPARISON_SCHEMA)
    assert summary["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert comparison["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert summary["$id"].endswith("/schemas/summary-v1.schema.json")
    assert comparison["$id"].endswith("/schemas/comparison-v1.schema.json")


def test_fresh_producer_summary_passes_schema(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs
    from benching.benchmark.contract import check_summary_invariants, validate_summary

    run_a = _synthetic_evidence(tmp_path, "bench-example-fireworks-a", "deepseek-v4", 10)
    summary = normalize_runs([run_a], write_comparison=False)["runs"][0]
    assert validate_summary(summary) == []
    assert check_summary_invariants(summary) == []
    assert summary["metric_revision"] == 2
    assert summary["tokenizer"]["available"] is True
    assert summary["speed"]["decode_tps"]["p50"] == 10.0


def test_fresh_producer_comparison_passes_schema_and_consistency(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs
    from benching.benchmark.contract import check_comparison_consistency, validate_comparison

    dir_a = _synthetic_evidence(tmp_path, "bench-example-fireworks-a", "deepseek-v4", 10)
    dir_b = _synthetic_evidence(tmp_path, "bench-example-fireworks-b", "glm-5.2", 90)
    comparison = normalize_runs([dir_a, dir_b], write_comparison=False)
    assert validate_comparison(comparison) == []
    assert check_comparison_consistency(comparison) == []
    assert comparison["tokenizer_identity_status"] == "known_equal"


def test_old_valid_fixtures_still_pass() -> None:
    from benching.benchmark.contract import check_summary_invariants, validate_comparison, validate_summary

    old_summary = json.loads((Path(__file__).parent / "fixtures" / "summary.json").read_text(encoding="utf-8"))
    assert validate_summary(old_summary) == []
    dashboard_summary = DASHBOARD / "data" / "summary.json"
    dashboard_comparison = DASHBOARD / "data" / "comparison-20260102.json"
    if not dashboard_summary.is_file():
        pytest.skip("benching-dashboard checkout not present")
    assert validate_summary(json.loads(dashboard_summary.read_text(encoding="utf-8"))) == []
    assert validate_comparison(json.loads(dashboard_comparison.read_text(encoding="utf-8"))) == []
    assert check_summary_invariants(old_summary) == []


def test_malformed_artifacts_fail_with_diagnostics() -> None:
    from benching.benchmark.contract import validate_comparison, validate_summary

    assert validate_summary({"speed": {}}) != []
    assert validate_summary({"schema_version": 1}) != []
    assert validate_summary({"schema_version": 1, "run_id": 42, "tasks": "nope"}) != []
    bad_version = {"schema_version": 2, "run_id": "x"}
    assert validate_summary(bad_version) != []
    assert validate_comparison({"schema_version": 1, "runs": []}) != []


def test_comparison_identity_mismatch_detected() -> None:
    from benching.benchmark.contract import check_comparison_consistency

    assert check_comparison_consistency({"runs": []}) != []
    comparison = {
        "run_ids": ["a", "b"],
        "runs": [{"run_id": "a"}, {"run_id": "C"}],
    }
    assert check_comparison_consistency(comparison) != []
    assert check_comparison_consistency({"run_ids": ["a"], "runs": [{"run_id": "a"}]}) == []


def test_invariant_violations_detected() -> None:
    from benching.benchmark.contract import check_summary_invariants

    assert check_summary_invariants({"reliability": {"success_rate": 2.0, "successful_requests": 1, "failed_requests": 0}, "tasks": [], "context": {}}) != []
    ok = {
        "reliability": {"success_rate": 1.0, "successful_requests": 1, "failed_requests": 0},
        "tasks": [{"task_id": "t", "trial_id": None, "passed": None, "reward": None}],
        "context": {"0-4K": {"requests": 1}, "unknown": {"requests": 0}},
    }
    assert check_summary_invariants(ok) == []
    bad_buckets = dict(ok)
    bad_buckets["context"] = {"0-4K": {"requests": 5}, "unknown": {"requests": 0}}
    assert check_summary_invariants(bad_buckets) != []


def test_producer_output_is_finite_json(tmp_path: Path) -> None:
    import json as strict_json

    from benching.analytics.analyze import normalize_runs

    directory = _synthetic_evidence(tmp_path, "bench-example-fireworks-a", "deepseek-v4", 10)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]

    def _reject_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")

    strict_json.loads(strict_json.dumps(summary), parse_constant=_reject_constant)


def test_run_id_ownership_and_missing_marker_contract(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs
    from benching.benchmark.contract import check_summary_invariants

    directory = _synthetic_evidence(tmp_path, "bench-example-fireworks-a", "deepseek-v4", 10)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    metrics = [json.loads(line) for line in (directory / "metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    assert metrics and all(row["run_id"] == summary["run_id"] for row in metrics)
    marker = {
        "task_id": "task-missing", "trial_id": None, "passed": None, "reward": None,
        "duration_sec": None, "exception": None, "timeout": None, "requests": 0,
        "tokens": {"input": None, "output": None, "cache_read": None, "cache_write": None},
        "latency": {"ttft_ms_mean": None, "ttft_ms_p50": None, "ttft_ms_p95": None, "end_to_end_latency_ms_mean": None},
        "reliability": {"successful_requests": 0, "failed_requests": 0, "success_rate": None},
    }
    assert check_summary_invariants({**summary, "tasks": [*summary["tasks"], marker]}) == []


def test_tokenizer_comparability_table() -> None:
    from benching.analytics.analyze import tokenizer_comparability

    known = {"tokenizer": {"repo": "o/r", "revision": "1"}}
    assert tokenizer_comparability([known, dict(known)]) == ("known_equal", True)
    assert tokenizer_comparability([known, {"tokenizer": {"repo": "o/other", "revision": "1"}}]) == ("known_different", False)
    assert tokenizer_comparability([{}, {}]) == ("unknown", False)
    assert tokenizer_comparability([{}, {}], tokenizer_override="/tmp/tok.json") == ("unknown", True)


def test_examples_match_producer(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    dir_a = _synthetic_evidence(tmp_path, "bench-example-fireworks-a", "deepseek-v4", 10)
    dir_b = _synthetic_evidence(tmp_path, "bench-example-fireworks-b", "glm-5.2", 90)
    comparison = normalize_runs([dir_a, dir_b], write_comparison=False)
    for run_id, suffix in (("bench-example-fireworks-a", "a"), ("bench-example-fireworks-b", "b")):
        regenerated = next(summary for summary in comparison["runs"] if summary["run_id"] == run_id)
        committed = json.loads((EXAMPLES / f"summary-fireworks-{suffix}.json").read_text(encoding="utf-8"))
        assert regenerated == committed
    committed_comparison = json.loads((EXAMPLES / "comparison-fireworks-ab.json").read_text(encoding="utf-8"))
    volatile = {"created_at_utc", "comparison_id"}
    assert {k: v for k, v in comparison.items() if k not in volatile} == {
        key: value for key, value in committed_comparison.items() if key not in volatile
    }
    assert committed_comparison["comparison_id"] == "comparison-fireworks-ab"
    assert committed_comparison["run_ids"] == ["bench-example-fireworks-a", "bench-example-fireworks-b"]


def test_examples_contain_no_machine_secrets() -> None:
    for name in ("run-a.json", "run-b.json", "summary-fireworks-a.json", "summary-fireworks-b.json", "comparison-fireworks-ab.json"):
        text = (EXAMPLES / name).read_text(encoding="utf-8")
        assert "auth_token" not in text
        assert "BEGIN " not in text
    for name in ("run-a.json", "run-b.json"):
        run_doc = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
        assert run_doc["tokenizer"]["local_cache"] is None


def test_schemas_in_sync_with_dashboard() -> None:
    import benching.benchmark

    dashboard_schemas = DASHBOARD / "schemas"
    if not dashboard_schemas.is_dir():
        pytest.skip("benching-dashboard schemas not present")
    package_schemas = Path(benching.benchmark.__file__).resolve().parent / "schemas"
    for name in ("summary-v1.schema.json", "comparison-v1.schema.json"):
        assert (package_schemas / name).read_bytes() == (dashboard_schemas / name).read_bytes()


def test_examples_in_sync_with_dashboard() -> None:
    dashboard_fixtures = DASHBOARD / "tests" / "fixtures"
    if not dashboard_fixtures.is_dir():
        pytest.skip("benching-dashboard fixtures not present")
    for name in ("summary-fireworks-a.json", "summary-fireworks-b.json", "comparison-fireworks-ab.json"):
        assert (EXAMPLES / name).read_bytes() == (dashboard_fixtures / name).read_bytes()

