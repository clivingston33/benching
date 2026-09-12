"""M1-task-4 fault-injection tests: truthful, atomic publication.

Deterministic only: failures are injected via monkeypatch around
os.replace / the analysis step / credential and registry writers — never
by filling disks or killing processes at random. No provider calls.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest


def _spec(tmp_path: Path):
    from benching.benchmark.config import BenchmarkSpec

    return BenchmarkSpec(
        name="suite", version="1", model="", reasoning="default", tasks_dir=tmp_path,
        expected_task_count=None, smoke_tasks=("task-a",),
        agent="benching.agents.instrumented_omp_agent:InstrumentedOmpAgent",
        max_tokens=None, context_window=None, run_id_prefix="bench",
        tokenizer_repo="", tokenizer_revision="", tokenizer_env_override=None,
        cache_dir=tmp_path,
    )


def _harness(tmp_path: Path, monkeypatch, analyze_behavior: str, cancel: threading.Event | None = None):
    """Mocked-preflight run_one. analyze_behavior: ok | raise | partial | ki."""
    import benching.benchmark.runner as runner

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "executable", lambda name: None)
    monkeypatch.setattr(runner, "validate_provider", lambda *a, **k: {"success": True})
    monkeypatch.setattr(runner, "task_names", lambda mode, spec: ["task-a"])
    monkeypatch.setattr(runner, "environment", lambda config, values=None: {})
    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *a, **k: {"source": "unavailable"})
    monkeypatch.setattr(runner, "harbor_command", lambda *a, **k: [sys.executable, "-c", "pass"])
    monkeypatch.setattr(runner, "start_proxy", lambda directory, port=8765, auth_token="", timeout=10.0: None)
    monkeypatch.setattr(runner, "benchmark_spec", lambda config: _spec(tmp_path))
    cfg = {
        "enabled": True, "env_file": str(tmp_path / "a.env"), "auth_env": "A_API_KEY",
        "base_url": "https://api.example.test/v1", "default_model": "m", "api": "openai-completions",
    }
    monkeypatch.setattr(runner, "provider_config", lambda name, root_config=None: ({}, cfg))
    monkeypatch.setattr(runner, "provider_env_values", lambda name, config: {"A_API_KEY": "dummy"})
    monkeypatch.setattr(runner, "resolve", lambda *a, **k: ("https://api.example.test/v1", "m"))
    monkeypatch.setattr(runner, "version", lambda name: None)
    monkeypatch.setattr(
        runner, "resolve_tokenizer_context",
        lambda root, spec, provider, model=None: {
            "provider": provider,
            "endpoint": "https://api.example.test/v1",
            "api_model": "m",
            "values": {"A_API_KEY": "dummy"},
            "model_settings": {},
            "metadata": {"source": "unavailable"},
        },
    )

    def _analyze(*args, **kwargs):
        run_dir = Path(args[0][-1])
        if analyze_behavior == "raise":
            (run_dir / "metrics.jsonl").write_text('{"value": 1}\n', encoding="utf-8")
            raise subprocess.CalledProcessError(1, ["analyze"])
        if analyze_behavior == "partial":
            (run_dir / "metrics.jsonl").write_text('{"value": 1}\n', encoding="utf-8")
            return None
        if analyze_behavior == "ki":
            if cancel is not None:
                cancel.set()
            raise KeyboardInterrupt
        (run_dir / "metrics.jsonl").write_text('{"value": 1}\n', encoding="utf-8")
        (run_dir / "summary.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
        return None

    monkeypatch.setattr(runner.subprocess, "run", _analyze)
    recorded: list = []
    real_set_status = runner.set_status

    def _recording_set_status(directory, status, **extra):
        recorded.append(status)
        return real_set_status(directory, status, **extra)

    monkeypatch.setattr(runner, "set_status", _recording_set_status)
    options = runner.RunOptions(provider="acme", mode="smoke")
    return runner, options, recorded


def _only_run_dir(tmp_path: Path) -> Path:
    dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(dirs) == 1
    return dirs[0]


# A. Completed only after analysis. --------------------------------------------

def test_analysis_failure_is_failed_not_completed(tmp_path, monkeypatch) -> None:
    runner, options, recorded = _harness(tmp_path, monkeypatch, "raise")
    with pytest.raises(subprocess.CalledProcessError):
        runner.run_one(options, {})
    directory = _only_run_dir(tmp_path)
    final = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    assert final["status"] == "failed"
    assert final.get("phase") == "analysis"
    assert "completed" not in recorded
    # Evidence preserved: run metadata + partial metrics remain, no summary fabricated.
    assert (directory / "run.json").is_file()
    assert (directory / "metrics.jsonl").is_file()
    assert not (directory / "summary.json").is_file()


# B. Successful lifecycle ordering. ----------------------------------------------

def test_success_reaches_created_running_analyzing_completed(tmp_path, monkeypatch) -> None:
    runner, options, recorded = _harness(tmp_path, monkeypatch, "ok")
    directory = runner.run_one(options, {})
    assert recorded == ["running", "running", "analyzing", "completed"]
    final = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    assert final["status"] == "completed"
    for name in ("run.json", "status.json", "metrics.jsonl", "summary.json"):
        assert (directory / name).is_file()


# C. Cancellation during analysis stays interrupted. ------------------------------

def test_cancel_during_analysis_is_interrupted_not_failed(tmp_path, monkeypatch) -> None:
    cancel = threading.Event()
    runner, options, recorded = _harness(tmp_path, monkeypatch, "ki", cancel)
    with pytest.raises(KeyboardInterrupt):
        runner.run_one(options, {}, cancel=cancel)
    assert recorded[-1] == "interrupted"
    assert "completed" not in recorded
    assert "failed" not in recorded
    directory = _only_run_dir(tmp_path)
    assert json.loads((directory / "status.json").read_text(encoding="utf-8"))["status"] == "interrupted"


# D. Atomic JSON under concurrent replacement. --------------------------------------

def test_atomic_json_readers_see_only_complete_documents(tmp_path) -> None:
    from benching.benchmark.io import dump_json_atomic

    target = tmp_path / "doc.json"
    doc_a = {"v": "A", "items": list(range(50))}
    doc_b = {"v": "B", "items": list(range(50, 100))}
    dump_json_atomic(target, doc_a)
    stop = threading.Event()
    failures: list = []

    def writer():
        for _ in range(100):
            dump_json_atomic(target, doc_b)
            dump_json_atomic(target, doc_a)
        stop.set()

    def reader():
        while not stop.is_set():
            try:
                text = target.read_text(encoding="utf-8")
            except OSError:
                # Transient Windows open/replace race on the reader side;
                # real pollers simply read again. Torn content would instead
                # surface below as JSONDecodeError or a document mismatch.
                time.sleep(0.005)
                continue
            try:
                seen = json.loads(text)
            except json.JSONDecodeError as exc:
                failures.append(exc)
                return
            if seen != doc_a and seen != doc_b:
                failures.append(ValueError(f"torn document observed: {str(seen)[:80]}"))
                return
            time.sleep(0)

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads)
    assert failures == []
    assert list(tmp_path.iterdir()) == [target]


# E. YAML replace failure preserves the original. -------------------------------------

def test_yaml_replace_failure_keeps_original_bytes(tmp_path, monkeypatch) -> None:
    from benching.benchmark.io import dump_yaml_atomic

    target = tmp_path / "reg.yaml"
    dump_yaml_atomic(target, {"providers": {"a": {"x": 1}}}, sort_keys=True)
    before = target.read_bytes()
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("injected disk failure")))
    with pytest.raises(OSError):
        dump_yaml_atomic(target, {"providers": {"a": {"x": 2}, "b": {}}}, sort_keys=True)
    assert target.read_bytes() == before
    import yaml

    assert yaml.safe_load(before) == {"providers": {"a": {"x": 1}}}


# F. Credential write failure. ----------------------------------------------------------

def test_rotation_failure_preserves_old_credential(tmp_path, monkeypatch) -> None:
    from benching.benchmark.providers import add_provider, rename_key_field
    from benching.benchmark.state import providers_dir

    add_provider("rot", "https://api.example.test/v1", "m", "first-secret", make_active=False)
    env_path = providers_dir() / "rot.env"
    before = env_path.read_bytes()
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        rename_key_field("rot", "second-secret")
    assert env_path.read_bytes() == before
    assert b"second-secret" not in env_path.read_bytes()


def test_registration_failure_leaves_no_credential_or_entry(tmp_path, monkeypatch) -> None:
    from benching.benchmark.providers import _load_registry, add_provider
    from benching.benchmark.state import providers_dir

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        add_provider("doomed", "https://api.example.test/v1", "m", "dummy-secret", make_active=False)
    assert "doomed" not in _load_registry()
    assert not (providers_dir() / "doomed.env").exists()


# G. Registry write failure preserves the old registry. ------------------------------------

def test_registry_replace_failure_keeps_valid_registry(tmp_path, monkeypatch) -> None:
    import yaml

    from benching.benchmark.providers import _load_registry, add_provider, update_provider
    from benching.benchmark.state import providers_registry_path

    add_provider("steady", "https://api.example.test/v1", "m", "dummy-secret", make_active=False)
    before = providers_registry_path().read_bytes()
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        update_provider("steady", default_model="m2")
    assert providers_registry_path().read_bytes() == before
    assert _load_registry()["steady"]["default_model"] == "m"
    assert yaml.safe_load(before)["providers"]["steady"]["default_model"] == "m"


# H. Same-second comparisons never collide. ----------------------------------------------------

def test_comparison_path_unique_within_same_second(tmp_path) -> None:
    import re

    from benching.analytics.analyze import comparison_path

    frozen = datetime(2026, 9, 8, 21, 0, 0, tzinfo=UTC)
    first = comparison_path(tmp_path, now=frozen)
    second = comparison_path(tmp_path, now=frozen)
    assert first != second
    assert re.fullmatch(r"comparison-\d{8}-\d{6}-\d{6}-[0-9a-f]{8}\.json", first.name)
    assert re.fullmatch(r"comparison-\d{8}-\d{6}-\d{6}-[0-9a-f]{8}\.json", second.name)


def test_same_second_comparisons_both_persist(tmp_path, monkeypatch) -> None:
    import benching.analytics.analyze as analyze_mod
    from benching.analytics.analyze import normalize_runs

    frozen = datetime(2026, 9, 8, 21, 0, 0, tzinfo=UTC)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(analyze_mod, "datetime", _FrozenDateTime)
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(json.dumps({"run_id": "r1", "benchmark": "b", "benchmark_version": "v"}), encoding="utf-8")
    (run_dir / "raw.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(analyze_mod, "runs_root", lambda: tmp_path)
    first = normalize_runs([run_dir], execution="sequential", write_comparison=True)
    second = normalize_runs([run_dir], execution="sequential", write_comparison=True)
    outputs = sorted(tmp_path.glob("comparison-*.json"))
    assert len(outputs) == 2
    for output in outputs:
        parsed = json.loads(output.read_text(encoding="utf-8"))
        assert parsed["run_ids"] == ["r1"]
    assert first["run_ids"] == second["run_ids"] == ["r1"]


# I. Publication failure is failed, not completed. --------------------------------------------------

def test_publication_failure_is_failed_not_completed(tmp_path, monkeypatch) -> None:
    runner, options, recorded = _harness(tmp_path, monkeypatch, "partial")
    with pytest.raises(SystemExit) as excinfo:
        runner.run_one(options, {})
    assert "summary.json" in str(excinfo.value.code or excinfo.value)
    assert "completed" not in recorded
    directory = _only_run_dir(tmp_path)
    final = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    assert final["status"] == "failed"
    assert final.get("phase") == "publication"


# J. Stale/abandoned run diagnostics. ---------------------------------------------------------------------

def _dead_pid() -> int:
    # A PID that was never assigned on this boot: os.kill(pid, 0) raises
    # OSError for it on both POSIX (ESRCH) and Windows (WinError 87).
    # Recently-reaped PIDs are avoided: Windows may still report them.
    for pid in (999999, 1999999, 2999999, 3999999):
        try:
            os.kill(pid, 0)
        except OSError:
            return pid
    raise AssertionError("could not obtain a dead pid for the stale fixture")


def _write_status(directory: Path, status: str, pid=None) -> None:
    payload: dict = {"status": status, "updated_at_utc": "2026-09-08T00:00:00Z"}
    if pid is not None:
        payload["pid"] = pid
    (directory / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def test_stale_running_with_dead_owner(tmp_path) -> None:
    from benching.benchmark.runs import describe_run

    directory = tmp_path / "old"
    directory.mkdir()
    (directory / "run.json").write_text("{}", encoding="utf-8")
    pid = _dead_pid()
    _write_status(directory, "running", pid)
    described = describe_run(directory)
    assert described["status"] == "running"
    assert described["stale"] is True
    assert str(pid) in described["detail"]
    assert "this host" in described["detail"]


def test_active_running_with_live_owner_not_stale(tmp_path) -> None:
    from benching.benchmark.lifecycle import spawn_owned, stop_process
    from benching.benchmark.runs import describe_run

    directory = tmp_path / "live"
    directory.mkdir()
    (directory / "run.json").write_text("{}", encoding="utf-8")
    # Detached like production run-owned children (benchmark.lifecycle).
    proc = spawn_owned([sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path)
    try:
        _write_status(directory, "analyzing", proc.pid)
        described = describe_run(directory)
        assert described["stale"] is False
        assert described["detail"] == ""
    finally:
        stop_process(proc)


def test_stale_running_without_recorded_owner(tmp_path) -> None:
    from benching.benchmark.runs import describe_run

    directory = tmp_path / "ownerless"
    directory.mkdir()
    (directory / "run.json").write_text("{}", encoding="utf-8")
    _write_status(directory, "running")
    described = describe_run(directory)
    assert described["stale"] is True
    assert "no owner" in described["detail"]


def test_terminal_and_unknown_states_never_stale(tmp_path) -> None:
    from benching.benchmark.runs import describe_run

    for name, payload in (
        ("done", {"status": "completed"}),
        ("bad", {"status": "failed"}),
        ("gone", {"status": "interrupted"}),
    ):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "run.json").write_text("{}", encoding="utf-8")
        (directory / "status.json").write_text(json.dumps(payload), encoding="utf-8")
        assert describe_run(directory)["stale"] is False
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "run.json").write_text("{}", encoding="utf-8")
    (corrupt / "status.json").write_text("{nope", encoding="utf-8")
    described = describe_run(corrupt)
    assert described["status"] == "unknown"
    assert described["stale"] is False


# K. Private auth artifact handling. ---------------------------------------------------------------------

def test_proxy_token_private_and_redacted(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner
    from benching.analytics.analyze import normalize_runs

    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *a, **k: {"source": "unavailable"})
    monkeypatch.setattr(runner, "version", lambda name: None)
    monkeypatch.setattr(runner, "executable", lambda name: name)
    token = "sekret-token-xyz-123"
    directory = runner.run_directory(
        runner.RunOptions(provider="acme", mode="smoke"),
        _spec(tmp_path),
        {"plan": None},
        "https://api.example.test/v1",
        "m",
        ["task-a"],
        proxy_auth_token=token,
    )
    auth_path = directory / "proxy-auth.json"
    assert json.loads(auth_path.read_text(encoding="utf-8")) == {"auth_token": token}
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(auth_path).st_mode) == 0o600
    for name in ("run.json", "proxy-routes.json", "status.json"):
        assert token not in (directory / name).read_text(encoding="utf-8")
    command = runner.harbor_command(
        runner.RunOptions(provider="acme", mode="smoke"),
        _spec(tmp_path),
        {"auth_env": "A_API_KEY", "api": "openai-completions", "plan": None},
        "https://api.example.test/v1",
        "m",
        directory,
        ["task-a"],
        proxy_auth_token=token,
    )
    assert any(element == f"proxy_auth_token={token}" for element in command)
    redacted = runner.redacted_command(command, token)
    assert not any(token in element for element in redacted)
    assert any(element == "proxy_auth_token=[REDACTED]" for element in redacted)
    (directory / "command.json").write_text(json.dumps(redacted), encoding="utf-8")
    assert token not in (directory / "command.json").read_text(encoding="utf-8")
    # Public artifacts never carry the token.
    (directory / "raw.jsonl").write_text("", encoding="utf-8")
    comparison = normalize_runs([directory], execution="sequential", write_comparison=True)
    assert token not in (directory / "summary.json").read_text(encoding="utf-8")
    assert token not in json.dumps(comparison)


# L. Canonical metrics unchanged by publication work. -------------------------------------------------------

def test_normalize_math_unchanged_on_synthetic_row(tmp_path) -> None:
    from benching.analytics.analyze import normalize, summarize

    row = {
        "event_type": "inference",
        "run_id": "r1",
        "provider": "acme",
        "task_id": "t",
        "trial_id": "1",
        "success": True,
        "stream_completed": True,
        "http_status": 200,
        "finish_reason": "stop",
        "timing": {
            "first_content_output_ms": 100.0,
            "last_content_output_ms": 300.0,
            "stream_completed_ms": 500.0,
        },
        "tokens": {
            "input_provider": 10,
            "output_provider": 4,
            "total_provider": 14,
            "cache_read": None,
            "cache_write": None,
        },
        "output_text": "hi",
        "output_text_truncated": False,
    }
    run = {"run_id": "r1", "provider": "acme", "benchmark": "b", "benchmark_version": "v"}
    normalized = normalize(run, [row], None)
    assert len(normalized) == 1
    entry = normalized[0]
    assert entry["tokens"]["input_provider"] == {"value": 10, "source": "reported"}
    assert entry["tokens"]["output_provider"] == {"value": 4, "source": "reported"}
    assert entry["timing"]["ttft_ms"] == {"value": 100.0, "source": "measured"}
    assert entry["timing"]["decode_duration_ms"] == {"value": 200.0, "source": "measured"}
    assert entry["timing"]["end_to_end_latency_ms"] == {"value": 500.0, "source": "measured"}
    assert entry["reliability"]["success"] is True
    summary = summarize(run, normalized, tmp_path)
    assert summary["requests"] == 1
    assert summary["reliability"]["request_success_rate"] == 1.0
    assert summary["reliability"]["stream_completion_rate"] == 1.0
    assert summary["reliability"]["provider_failures"] == 0
    assert summary["tokens"]["input_provider"] == 10
    assert summary["tokens"]["output_provider"] == 4
    assert summary["timing"]["ttft_ms"]["mean"] == 100.0
    assert summary["timing"]["decode_duration_ms"]["mean"] == 200.0
    assert summary["timing"]["end_to_end_latency_ms"]["mean"] == 500.0


# Reader resilience: corrupt history must not break discovery. --------------------------------------------------

def test_corrupt_run_does_not_break_discovery(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner
    from benching.benchmark import runs as runs_mod
    from benching.benchmark.results import summary_for

    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    monkeypatch.setattr(runs_mod, "runs_root", lambda: tmp_path)
    bad = tmp_path / "bench-bad"
    bad.mkdir()
    (bad / "run.json").write_text('{"run_id": "bad"}', encoding="utf-8")
    (bad / "status.json").write_text("{nope", encoding="utf-8")
    (bad / "summary.json").write_text("{{{", encoding="utf-8")
    good = tmp_path / "bench-good"
    good.mkdir()
    (good / "run.json").write_text('{"run_id": "good", "provider": "acme"}', encoding="utf-8")
    (good / "status.json").write_text('{"status": "completed"}', encoding="utf-8")
    (good / "summary.json").write_text('{"schema_version": 1}', encoding="utf-8")
    names = sorted(path.name for path in runs_mod.all_run_dirs())
    assert names == ["bench-bad", "bench-good"]
    assert runs_mod.status(bad) == "unknown"
    assert runs_mod.describe_run(bad)["stale"] is False
    assert summary_for(bad) is None
    assert runs_mod.status(good) == "completed"


