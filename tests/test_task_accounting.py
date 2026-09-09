"""M2-task-6 tests: run independence and complete task accounting.

Deterministic only: synthetic run directories, fault-injected writers,
scripted clocks. No provider calls, no sleeps, no wall-clock assertions.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest


def _write_run(
    root: Path,
    name: str,
    *,
    tasks: list[str] | None = None,
    trials: int | None = 1,
    tokenizer: tuple | None = None,
    provider: str = "acme",
    model: str = "model-a",
) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "harbor").mkdir(exist_ok=True)
    run: dict = {
        "run_id": name,
        "created_at_utc": "2026-09-08T00:00:00Z",
        "benchmark": "suite",
        "benchmark_version": "1.0",
        "task_count": len(tasks) if tasks is not None else 1,
        "provider": provider,
        "model": model,
        "api_model": model,
        "reasoning_mode": "default",
        "concurrency": 1,
        "streaming": True,
        "proxy_schema_version": 1,
    }
    if tasks is not None:
        run["tasks"] = tasks
    if trials is not None:
        run["trials"] = trials
    if tokenizer is not None:
        run["tokenizer"] = {"repo": tokenizer[0], "revision": tokenizer[1], "local_cache": tokenizer[2]}
    (directory / "run.json").write_text(json.dumps(run), encoding="utf-8")
    return directory


def _telemetry_row(task: str, trial: str | None, request: str, *, tokens: int | None = 100) -> dict:
    return {
        "event_type": "inference",
        "run_id": "r",
        "request_id": request,
        "provider": "acme",
        "task_id": task,
        "trial_id": trial,
        "model": "model-a",
        "timing": {"first_content_output_ms": 10.0, "last_content_output_ms": 20.0, "stream_completed_ms": 30.0},
        "tokens": {"input_provider": tokens, "output_provider": 5, "total_provider": (tokens or 0) + 5, "cache_read": None, "cache_write": None},
        "output_text": "hello",
        "output_text_truncated": False,
        "success": True,
        "stream_completed": True,
        "http_status": 200,
    }


def _write_raw(directory: Path, rows: list[dict]) -> None:
    (directory / "raw.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_harbor(directory: Path, subdir: str, task: str, trial: str | None, *, reward=None, exception=None) -> None:
    target = directory / "harbor" / subdir
    target.mkdir(parents=True, exist_ok=True)
    data: dict = {"task_name": task, "verifier_result": {}, "exception_info": {}}
    if trial is not None:
        data["trial_id"] = trial
    if reward is not None:
        data["verifier_result"] = {"rewards": {"reward": reward}}
    if exception is not None:
        data["exception_info"] = {"exception_type": exception}
    (target / "result.json").write_text(json.dumps(data), encoding="utf-8")


def _write_tokenizer(path: Path, words: dict[str, int]) -> str:
    from tokenizers import Tokenizer, models

    Tokenizer(models.WordLevel(words, unk_token="[UNK]")).save(str(path))
    return str(path)


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {name: (directory / name).read_bytes() for name in ("run.json", "metrics.jsonl", "summary.json")}


# A. Comparison never mutates its inputs (primary C3 regression test). ----------

def test_comparison_leaves_standalone_artifacts_untouched(tmp_path: Path, monkeypatch) -> None:
    import benching.analytics.analyze as analyze_mod
    from benching.analytics.analyze import normalize_runs

    monkeypatch.setattr(analyze_mod, "runs_root", lambda: tmp_path)
    cache_a = _write_tokenizer(tmp_path / "tok-a.json", {"hello": 0, "[UNK]": 1})
    run_a = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1, tokenizer=("org/a", "rev-a", cache_a))
    _write_raw(run_a, [_telemetry_row("task-a", "trial-1", "req-a")])
    run_b = _write_run(tmp_path, "run-b", tasks=["task-a"], trials=1, tokenizer=("org/b", "rev-b", str(tmp_path / "missing")))
    _write_raw(run_b, [_telemetry_row("task-a", "trial-1", "req-b")])

    normalize_runs([run_a], write_comparison=False)
    before_a = _snapshot(run_a)
    metrics_a = [json.loads(line) for line in (run_a / "metrics.jsonl").read_text().splitlines()]
    assert metrics_a[0]["tokens"]["output_local"] == {"value": 1, "source": "calculated"}

    comparison = normalize_runs([run_a, run_b], write_comparison=True)
    assert comparison["tokenizers_comparable"] is False
    assert comparison["tokenizer_identity_status"] == "known_different"
    assert _snapshot(run_a) == before_a
    after_a = [json.loads(line) for line in (run_a / "metrics.jsonl").read_text().splitlines()]
    assert after_a[0]["tokens"]["output_local"] == {"value": 1, "source": "calculated"}
    assert len(list(tmp_path.glob("comparison-*.json"))) == 1


# B. Same-tokenizer comparison stays comparable without rewriting. ---------------

def test_same_tokenizer_comparison_without_rewrite(tmp_path: Path, monkeypatch) -> None:
    import benching.analytics.analyze as analyze_mod
    from benching.analytics.analyze import analyze_run, normalize_runs

    monkeypatch.setattr(analyze_mod, "runs_root", lambda: tmp_path)
    cache = _write_tokenizer(tmp_path / "tok.json", {"hello": 0, "[UNK]": 1})
    dirs = []
    for name in ("run-a", "run-b"):
        directory = _write_run(tmp_path, name, tasks=["task-a"], trials=1, tokenizer=("org/same", "rev", cache))
        _write_raw(directory, [_telemetry_row("task-a", "trial-1", f"req-{name}")])
        analyze_run(directory, json.loads((directory / "run.json").read_text()))
        dirs.append(directory)
    before = {d.name: _snapshot(d) for d in dirs}
    comparison = normalize_runs(dirs, write_comparison=True)
    assert comparison["tokenizers_comparable"] is True
    assert comparison["tokenizer_identity_status"] == "known_equal"
    assert {d.name: _snapshot(d) for d in dirs} == before


# C. Unknown identities are unknown, never proven equal. --------------------------

def test_unknown_tokenizer_identities_are_not_equal(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs, tokenizer_comparability

    assert tokenizer_comparability([{}, {}]) == ("unknown", False)
    assert tokenizer_comparability([{"tokenizer": {"repo": "o/r", "revision": "1"}}, {}]) == ("unknown", False)
    assert tokenizer_comparability(
        [{"tokenizer": {"repo": "o/r", "revision": "1"}}, {"tokenizer": {"repo": "o/r", "revision": "1"}}]
    ) == ("known_equal", True)
    run_a = _write_run(tmp_path, "run-a", tasks=["task-a"])
    _write_raw(run_a, [_telemetry_row("task-a", "trial-1", "req-a")])
    run_b = _write_run(tmp_path, "run-b", tasks=["task-a"])
    _write_raw(run_b, [_telemetry_row("task-a", "trial-1", "req-b")])
    comparison = normalize_runs([run_a, run_b], write_comparison=False)
    assert comparison["tokenizer_identity_status"] == "unknown"
    assert comparison["tokenizers_comparable"] is False


# D. Result viewing is read-only. ----------------------------------------------------

def test_result_viewing_does_not_rewrite_artifacts(tmp_path: Path, monkeypatch) -> None:
    import benching.benchmark.runs as runs_mod
    from benching.analytics.analyze import analyze_run
    from benching.benchmark.results import load_result, summary_for

    monkeypatch.setattr(runs_mod, "runs_root", lambda: tmp_path)
    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    _write_raw(directory, [_telemetry_row("task-a", "trial-1", "req-a")])
    analyze_run(directory, json.loads((directory / "run.json").read_text()))
    before = _snapshot(directory)
    for _ in range(2):
        found, summary = load_result("latest")
        assert found == directory
        assert summary is not None
        assert summary_for(directory) is not None
    assert _snapshot(directory) == before


# E/F/G. Planned, missing, and multiple trials. -----------------------------------------

def test_missing_planned_task_is_explicit_not_failed(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a", "task-b"], trials=1)
    _write_raw(directory, [_telemetry_row("task-a", "trial-0", "req-a")])
    _write_harbor(directory, "job-a", "task-a", "trial-0", reward=1.0)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    by_key = {(task["task_id"], task["trial_id"]): task for task in summary["tasks"]}
    assert by_key[("task-a", "trial-0")]["passed"] is True
    missing = by_key[("task-b", None)]
    assert missing["requests"] == 0
    assert missing["passed"] is None
    assert missing["reward"] is None
    assert missing["timeout"] is None or missing["timeout"] is False
    assert missing["exception"] is None


def test_two_trials_remain_two_everywhere(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs
    from benching.benchmark.runs import task_counts
    from benching.benchmark.status import scan_harbor_results

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=2)
    _write_raw(directory, [
        _telemetry_row("task-a", "t0", "req-0"),
        _telemetry_row("task-a", "t1", "req-1"),
    ])
    _write_harbor(directory, "job-0", "task-a", "t0", reward=1.0)
    _write_harbor(directory, "job-1", "task-a", "t1", reward=0.0)
    assert set(scan_harbor_results(directory / "harbor")) == {("task-a", "t0"), ("task-a", "t1")}
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    by_key = {(task["task_id"], task["trial_id"]): task for task in summary["tasks"]}
    assert by_key[("task-a", "t0")]["passed"] is True
    assert by_key[("task-a", "t1")]["passed"] is False
    assert task_counts(directory)["passed"] == 1
    assert task_counts(directory)["failed"] == 1


def test_missing_one_of_three_attempts(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=3)
    _write_raw(directory, [
        _telemetry_row("task-a", "ta", "req-a"),
        _telemetry_row("task-a", "tb", "req-b"),
    ])
    _write_harbor(directory, "job-a", "task-a", "ta", reward=1.0)
    _write_harbor(directory, "job-b", "task-a", "tb", reward=1.0)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    entries = [task for task in summary["tasks"] if task["task_id"] == "task-a"]
    assert len(entries) == 3
    missing = [task for task in entries if task["trial_id"] is None]
    assert len(missing) == 1
    assert missing[0]["requests"] == 0
    assert missing[0]["passed"] is None


# H/I. Duplicate telemetry. ---------------------------------------------------------------

def test_exact_duplicate_telemetry_row_deduplicated(tmp_path: Path, capsys) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    row = _telemetry_row("task-a", "trial-1", "req-same")
    _write_raw(directory, [row, dict(row)])
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    metrics = [(directory / "metrics.jsonl").read_text().splitlines()]
    assert len(metrics[0]) == 1
    assert summary["tokens"]["input_provider"] == 100
    assert "duplicate telemetry row ignored" in capsys.readouterr().err


def test_conflicting_duplicate_telemetry_fails(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    first = _telemetry_row("task-a", "trial-1", "req-same")
    second = dict(first)
    second["output_text"] = "different output"
    _write_raw(directory, [first, second])
    with pytest.raises(SystemExit, match="duplicate request identity"):
        normalize_runs([directory], write_comparison=False)


# J. Duplicate Harbor results. ------------------------------------------------------------------

def test_identical_duplicate_harbor_result_keeps_one(tmp_path: Path, capsys) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    _write_raw(directory, [_telemetry_row("task-a", "trial-1", "req-a")])
    _write_harbor(directory, "job-1", "task-a", "trial-1", reward=1.0)
    _write_harbor(directory, "job-2", "task-a", "trial-1", reward=1.0)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    assert [(t["task_id"], t["trial_id"]) for t in summary["tasks"] if t["task_id"] == "task-a"] == [("task-a", "trial-1")]
    assert "duplicate Harbor result ignored" in capsys.readouterr().err


def test_conflicting_duplicate_harbor_result_fails(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    _write_raw(directory, [_telemetry_row("task-a", "trial-1", "req-a")])
    _write_harbor(directory, "job-1", "task-a", "trial-1", reward=1.0)
    _write_harbor(directory, "job-2", "task-a", "trial-1", reward=0.0)
    with pytest.raises(SystemExit, match="duplicate Harbor result identity"):
        normalize_runs([directory], write_comparison=False)


# K/L. Malformed evidence. ----------------------------------------------------------------------------

def test_malformed_raw_jsonl_fails_with_line(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    lines = [
        json.dumps(_telemetry_row("task-a", "trial-1", "req-1")),
        "",
        json.dumps(_telemetry_row("task-a", "trial-1", "req-2")),
    ]
    (directory / "raw.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    normalize_runs([directory], write_comparison=False)
    with (directory / "raw.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{not valid json\n")
    with pytest.raises(SystemExit, match=r"raw\.jsonl at line 4"):
        normalize_runs([directory], write_comparison=False)
    with pytest.raises(SystemExit, match=r"raw\.jsonl at line 2"):
        (directory / "raw.jsonl").write_text('{"event_type": "oops"}\n[1, 2]\n', encoding="utf-8")
        normalize_runs([directory], write_comparison=False)


def test_malformed_harbor_result_fails_with_path(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    _write_raw(directory, [_telemetry_row("task-a", "trial-1", "req-a")])
    bad = directory / "harbor" / "job-bad"
    bad.mkdir(parents=True)
    (bad / "result.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit, match="malformed Harbor result"):
        normalize_runs([directory], write_comparison=False)
    (bad / "result.json").write_text(json.dumps({"stats": {}, "n_total_trials": 0}), encoding="utf-8")
    normalize_runs([directory], write_comparison=False)


# M. Numeric reward preservation. --------------------------------------------------------------------------

def test_non_binary_reward_preserved_exactly(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    _write_raw(directory, [_telemetry_row("task-a", "trial-1", "req-a")])
    _write_harbor(directory, "job-1", "task-a", "trial-1", reward=0.5)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    assert summary["tasks"][0]["reward"] == 0.5
    assert summary["tasks"][0]["passed"] is False


# N/O. Context accounting. ---------------------------------------------------------------------------------------

def test_unknown_context_counted_explicitly(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    _write_raw(directory, [
        _telemetry_row("task-a", "t-known", "req-1", tokens=100),
        _telemetry_row("task-a", "t-unknown", "req-2", tokens=None),
    ])
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    context = summary["context"]
    assert context["unknown"]["requests"] == 1
    total = sum(bucket["requests"] for bucket in context.values())
    assert total == 2
    assert context["0-4K"]["requests"] == 1


def test_context_bucket_boundaries_exact(tmp_path: Path) -> None:
    from benching.analytics.analyze import normalize_runs

    directory = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1)
    counts = [0, 4095, 4096, 16383, 16384, None, True]
    rows = [_telemetry_row("task-a", f"t{i}", f"req-{i}", tokens=value) for i, value in enumerate(counts)]
    _write_raw(directory, rows)
    summary = normalize_runs([directory], write_comparison=False)["runs"][0]
    context = summary["context"]
    assert context["0-4K"]["requests"] == 2
    assert context["4K-16K"]["requests"] == 2
    assert context["16K-32K"]["requests"] == 1
    assert context["32K-64K"]["requests"] == 0
    assert context["64K+"]["requests"] == 0
    assert context["unknown"]["requests"] == 2
    assert sum(bucket["requests"] for bucket in context.values()) == len(counts)


# P. Concurrency overlap from real intervals. ------------------------------------------------------------------------

class _InstantResponse:
    status = 200
    headers: dict = {}

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._consumed = False

    def read(self, size: int = -1) -> bytes:
        if self._consumed:
            return b""
        self._consumed = True
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _sse_ok_bytes() -> bytes:
    return b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'


def test_probe_measures_post_barrier_intervals(monkeypatch) -> None:
    import benching.benchmark.concurrency as probe

    calls = iter([100.0, 100.5, 102.0, 103.0])

    def fake_monotonic() -> float:
        try:
            return next(calls)
        except StopIteration:
            return 103.0

    monkeypatch.setattr(probe.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(probe, "urlopen", lambda request, timeout=None: _InstantResponse(_sse_ok_bytes()))
    barrier = threading.Barrier(1)
    result = probe.one_request("acme", None, "unknown", "https://example.test/v1", "m", "secret", 1, 0, barrier)
    assert result["stream_success"] is True
    assert result["ttft_ms"] == 500.0
    assert result["e2e_latency_ms"] == 2000.0
    assert result["exec_start_mono"] == 100.0
    assert result["exec_end_mono"] == 103.0


def test_overlap_counts_from_actual_intervals() -> None:
    from benching.benchmark.concurrency import _max_overlap

    assert _max_overlap([(0.0, 2.0), (1.0, 3.0)]) == 2
    assert _max_overlap([(0.0, 1.0), (2.0, 3.0)]) == 1
    assert _max_overlap([]) == 0


# Q. plan_tier round-trip. -----------------------------------------------------------------------------------------------

def test_plan_tier_survives_route_loading(tmp_path: Path) -> None:
    from benching.proxy.telemetry_proxy import load_routes

    path = tmp_path / "routes.json"
    path.write_text(json.dumps({
        "acme": {"upstream": "https://api.example.test/v1", "plan": "pro", "plan_tier": "Scale", "reasoning": "default"},
        "bare": {"upstream": "https://api.example.test/v1"},
    }), encoding="utf-8")
    routes = load_routes(path)
    assert routes["acme"]["plan_tier"] == "Scale"
    assert routes["bare"]["plan_tier"] == "unknown"


# R. Suite prefix normalization. ---------------------------------------------------------------------------------------------

def test_harbor_prefix_normalization_is_scoped() -> None:
    from benching.benchmark.status import normalize_harbor_task_id

    assert normalize_harbor_task_id("terminal-bench/task-a") == "task-a"
    assert normalize_harbor_task_id("other-suite/task-a") == "other-suite/task-a"
    assert normalize_harbor_task_id("a/terminal-bench/b") == "a/terminal-bench/b"
    assert normalize_harbor_task_id("") == ""
    assert normalize_harbor_task_id(None) == ""


# S. Golden summary regression. ---------------------------------------------------------------------------------------------------

def test_golden_summary_metrics_stable(tmp_path: Path, monkeypatch) -> None:
    import benching.analytics.analyze as analyze_mod
    from benching.analytics.analyze import normalize_runs

    monkeypatch.setattr(analyze_mod, "runs_root", lambda: tmp_path)
    cache = _write_tokenizer(tmp_path / "tok.json", {"hello": 0, "[UNK]": 1})
    directory = _write_run(
        tmp_path, "run-a", tasks=["task-a"], trials=1,
        tokenizer=("org/tok", "rev-1", cache), provider="acme", model="model-a",
    )
    _write_raw(directory, [_telemetry_row("task-a", "trial-1", "req-a")])
    _write_harbor(directory, "job-1", "task-a", "trial-1", reward=1.0)
    comparison = normalize_runs([directory], write_comparison=True)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    assert summary["tokens"]["input_provider"] == 100
    assert summary["tokens"]["output_local"] == 1
    assert summary["reliability"]["success_rate"] == 1.0
    assert summary["score"]["value"] == 1.0
    assert summary["tasks"][0]["passed"] is True
    assert summary["tasks"][0]["reward"] == 1.0
    assert comparison["run_ids"] == ["run-a"]
    assert comparison["models"] == ["model-a"]
    assert comparison["execution_mode"] == "sequential"
    assert comparison["official_comparison"] is True
    assert comparison["tokenizers_comparable"] is True
    assert comparison["tokenizer_identity_status"] == "known_equal"


# Immutability invariant. --------------------------------------------------------------------------------------------------------------

def test_read_paths_never_mutate_standalone_artifacts(tmp_path: Path, monkeypatch) -> None:
    import benching.analytics.analyze as analyze_mod
    import benching.benchmark.runs as runs_mod
    from benching.analytics.analyze import analyze_run, normalize_runs
    from benching.benchmark.results import load_result, summary_for

    monkeypatch.setattr(analyze_mod, "runs_root", lambda: tmp_path)

    monkeypatch.setattr(runs_mod, "runs_root", lambda: tmp_path)
    cache = _write_tokenizer(tmp_path / "tok.json", {"hello": 0, "[UNK]": 1})
    run_a = _write_run(tmp_path, "run-a", tasks=["task-a"], trials=1, tokenizer=("org/a", "rev-a", cache))
    _write_raw(run_a, [_telemetry_row("task-a", "trial-1", "req-a")])
    run_b = _write_run(tmp_path, "run-b", tasks=["task-a"], trials=1)
    _write_raw(run_b, [_telemetry_row("task-a", "trial-1", "req-b")])
    analyze_run(run_a, json.loads((run_a / "run.json").read_text()))
    analyze_run(run_b, json.loads((run_b / "run.json").read_text()))
    snapshots = {run_a.name: _snapshot(run_a), run_b.name: _snapshot(run_b)}
    normalize_runs([run_a, run_b], write_comparison=True)
    load_result("latest")
    summary_for(run_a)
    list(runs_mod.all_run_dirs())
    assert _snapshot(run_a) == snapshots[run_a.name]
    assert _snapshot(run_b) == snapshots[run_b.name]
    assert len(list(tmp_path.glob("comparison-*.json"))) == 1

