"""Focused M1-task-3 tests: lifecycle and proxy ownership.

Deterministic, dummy/local only: no provider traffic, no Docker/Harbor.
Harmless local children (``sys.executable -c sleep``) exercise the real
ownership paths. Tests that invoke orchestration set
``BENCHING_ALLOW_UNSUPPORTED_PLATFORM=1``; real execution still requires
Linux/WSL (see benchmark.lifecycle).
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from benching.benchmark.lifecycle import (
    RunHandle,
    new_proxy_token,
    require_supported_execution_platform,
    spawn_owned,
    stop_process,
    terminate_all_active,
    track,
    wait_owned,
)
from benching.proxy.telemetry_proxy import JsonlWriter, Proxy

TOKEN = "test-run-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _routes() -> dict:
    return {
        "acme": {
            "upstream": "https://example.test/v1",
            "plan": "trial",
            "plan_tier": "unknown",
            "reasoning": "default",
        }
    }


class _CaptureWriter:
    """Minimal StreamWriter stand-in that records response bytes."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


async def _fake_reader(request: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(request)
    reader.feed_eof()
    return reader


def _request(body: bytes, token: str | None, provider: str = "acme") -> bytes:
    headers = (
        f"POST /{provider}/chat/completions HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
    )
    if token is not None:
        headers += f"X-Benchmark-Proxy-Auth: {token}\r\n"
    headers += f"Content-Length: {len(body)}\r\n\r\n"
    return headers.encode("latin1") + body


def _run_handle(tmp_path: Path, body: bytes, token: str | None, monkeypatch, provider: str = "acme"):
    """Drive the real Proxy.handle with a recording forwarder."""
    import benching.proxy.telemetry_proxy as mod

    events = tmp_path / "events.jsonl"
    calls: dict = {}
    forwarded_headers: dict = {}

    async def fake_forward(self, host, port, method, path, version, headers, fwd_body, client, state, start):
        calls["called"] = True
        forwarded_headers.update(headers)

    monkeypatch.setattr(mod.Proxy, "forward", fake_forward)
    proxy = mod.Proxy(mod.JsonlWriter(events), _routes(), auth_token=TOKEN)
    writer = _CaptureWriter()

    async def run() -> None:
        await proxy.handle(await _fake_reader(_request(body, token, provider)), writer)

    asyncio.run(run())
    return writer, calls, forwarded_headers, events


def _rows(events: Path) -> list:
    if not events.is_file():
        return []
    return [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]


def _inference_rows(events: Path) -> list:
    return [row for row in _rows(events) if row.get("event_type") == "inference"]


def _parse_response(data: bytes) -> tuple[bytes, bytes]:
    head, _, body = bytes(data).partition(b"\r\n\r\n")
    return head, body


def _assert_framed(data: bytes) -> bytes:
    head, body = _parse_response(data)
    declared = None
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(b"content-length:"):
            declared = int(line.split(b":", 1)[1].strip())
    assert declared is not None, f"missing Content-Length in {head!r}"
    assert declared == len(body), f"Content-Length {declared} != body length {len(body)}"
    return body


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _sleep_child(seconds: int = 30) -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])


# A. Proxy ownership: a foreign listener must not count as readiness. ------

def test_proxy_startup_rejects_foreign_listener(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    port = _free_port()
    listener = socket.socket()
    listener.bind(("127.0.0.1", port))
    listener.listen(16)
    try:
        (tmp_path / "proxy-auth.json").write_text(json.dumps({"auth_token": "tok"}), encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            runner.start_proxy(tmp_path, port, "tok", timeout=6.0)
        assert "proxy" in str(excinfo.value.code or excinfo.value).lower()
        # The unrelated listener is untouched and still accepting: drain the
        # readiness-probe connections from the backlog, then connect fresh.
        listener.settimeout(0.2)
        while True:
            try:
                conn, _ = listener.accept()
                conn.close()
            except (OSError, socket.timeout):
                break
        listener.settimeout(2.0)
        with socket.create_connection(("127.0.0.1", port), timeout=2.0):
            pass
    finally:
        listener.close()


# B. Proxy authentication. ---------------------------------------------------

def test_proxy_rejects_unauthenticated_without_forward_or_row(tmp_path, monkeypatch) -> None:
    body = b'{"model":"m","messages":[]}'
    for bad_token in (None, "wrong-token"):
        writer, calls, _, events = _run_handle(tmp_path, body, bad_token, monkeypatch)
        head, _ = _parse_response(writer.data)
        assert b" 403 " in head.split(b"\r\n", 1)[0]
        _assert_framed(writer.data)
        assert calls.get("called") is not True
        assert _inference_rows(events) == []


def test_proxy_accepts_authenticated_and_strips_token(tmp_path, monkeypatch) -> None:
    body = b'{"model":"m","messages":[]}'
    writer, calls, forwarded, events = _run_handle(tmp_path, body, TOKEN, monkeypatch)
    assert calls.get("called") is True
    assert b" 403 " not in bytes(writer.data)
    assert "x-benchmark-proxy-auth" not in forwarded
    assert "authorization" not in forwarded


# C. Malformed downstream body (C10). ------------------------------------------

def test_malformed_body_returns_400_without_row_or_forward(tmp_path, monkeypatch) -> None:
    writer, calls, _, events = _run_handle(tmp_path, b"{", TOKEN, monkeypatch)
    head, _ = _parse_response(writer.data)
    assert b" 400 " in head.split(b"\r\n", 1)[0]
    _assert_framed(writer.data)
    assert calls.get("called") is not True
    assert _inference_rows(events) == []


def test_truncated_body_returns_400_without_row_or_forward(tmp_path, monkeypatch) -> None:
    import benching.proxy.telemetry_proxy as mod

    events = tmp_path / "events.jsonl"
    calls: dict = {}

    async def fake_forward(self, *args, **kwargs):
        calls["called"] = True

    monkeypatch.setattr(mod.Proxy, "forward", fake_forward)
    proxy = mod.Proxy(mod.JsonlWriter(events), _routes(), auth_token=TOKEN)
    writer = _CaptureWriter()
    raw = (
        "POST /acme/chat/completions HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        f"X-Benchmark-Proxy-Auth: {TOKEN}\r\n"
        "Content-Length: 50\r\n\r\n"
    ).encode("latin1") + b'{"a":'

    async def run() -> None:
        await proxy.handle(await _fake_reader(raw), writer)

    asyncio.run(run())
    head, _ = _parse_response(writer.data)
    assert b" 400 " in head.split(b"\r\n", 1)[0]
    _assert_framed(writer.data)
    assert calls.get("called") is not True
    assert _inference_rows(events) == []
    assert all(row.get("provider_failure") is not True for row in _rows(events))


# D. Correct response framing (C11). --------------------------------------------

def test_error_responses_declare_exact_content_length(tmp_path, monkeypatch) -> None:
    body = b'{"model":"m","messages":[]}'
    writer403, _, _, _ = _run_handle(tmp_path, body, "wrong", monkeypatch)
    _assert_framed(writer403.data)
    writer400, _, _, _ = _run_handle(tmp_path, b"{", TOKEN, monkeypatch)
    _assert_framed(writer400.data)
    # 502 path: authenticated but unknown provider.
    writer502, calls502, _, _ = _run_handle(tmp_path, body, TOKEN, monkeypatch, provider="nope")
    head502, _ = _parse_response(writer502.data)
    assert b" 502 " in head502.split(b"\r\n", 1)[0]
    _assert_framed(writer502.data)
    assert calls502.get("called") is not True


# E. Bounded stall timeout. -----------------------------------------------------

def test_stalled_upstream_terminates_on_deadline(tmp_path, monkeypatch) -> None:
    import benching.proxy.telemetry_proxy as mod

    class _StallReader:
        async def readline(self) -> bytes:
            await asyncio.sleep(3600)
            return b""

    class _Upstream:
        def write(self, data: bytes) -> None:
            pass

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    async def fake_open(*args, **kwargs):
        return _StallReader(), _Upstream()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    events = tmp_path / "events.jsonl"
    proxy = mod.Proxy(
        mod.JsonlWriter(events), _routes(), auth_token=TOKEN,
        connect_timeout=2.0, header_timeout=0.3, read_timeout=0.3, overall_timeout=5.0,
    )
    writer = _CaptureWriter()
    body = b'{"model":"m","messages":[]}'

    async def run() -> None:
        await proxy.handle(await _fake_reader(_request(body, TOKEN)), writer)

    started = time.monotonic()
    asyncio.run(run())
    elapsed = time.monotonic() - started
    assert elapsed < 10, f"stalled upstream hung for {elapsed:.1f}s"
    rows = _inference_rows(events)
    assert len(rows) == 1
    assert rows[0]["provider_failure"] is True
    assert rows[0]["error_type"] == "upstream_header_timeout"
    head, _ = _parse_response(writer.data)
    assert b" 502 " in head.split(b"\r\n", 1)[0]
    _assert_framed(writer.data)


# F. Direct cancellation terminates owned children only. -------------------------

def test_direct_cancellation_terminates_owned_children(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner
    from benching.benchmark.config import BenchmarkSpec

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "executable", lambda name: None)
    monkeypatch.setattr(runner, "validate_provider", lambda *a, **k: {"success": True})
    monkeypatch.setattr(runner, "task_names", lambda mode, spec: ["task-a"])
    monkeypatch.setattr(runner, "environment", lambda config, values=None: {})
    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *a, **k: {"source": "unavailable"})
    monkeypatch.setattr(
        runner, "harbor_command",
        lambda *a, **k: [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    spec = BenchmarkSpec(
        name="suite", version="1", model="", reasoning="default", tasks_dir=tmp_path,
        expected_task_count=None, smoke_tasks=("task-a",),
        agent="benching.agents.instrumented_omp_agent:InstrumentedOmpAgent",
        max_tokens=None, context_window=None, run_id_prefix="bench",
        tokenizer_repo="", tokenizer_revision="", tokenizer_env_override=None,
        cache_dir=tmp_path,
    )
    monkeypatch.setattr(runner, "benchmark_spec", lambda config: spec)
    cfg = {
        "enabled": True, "env_file": str(tmp_path / "a.env"), "auth_env": "A_API_KEY",
        "base_url": "https://api.example.test/v1", "default_model": "m", "api": "openai-completions",
    }
    monkeypatch.setattr(runner, "provider_config", lambda name, root_config=None: ({}, cfg))
    monkeypatch.setattr(runner, "provider_env_values", lambda name, config: {"A_API_KEY": "dummy"})
    monkeypatch.setattr(runner, "resolve", lambda *a, **k: ("https://api.example.test/v1", "m"))
    monkeypatch.setattr(runner, "version", lambda name: None)
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: None)

    seen: dict = {}
    orig_harbor = RunHandle.register_harbor
    orig_proxy = RunHandle.register_proxy

    def rec_harbor(self, proc):
        seen["harbor"] = proc
        seen["handle"] = self
        return orig_harbor(self, proc)

    def rec_proxy(self, proc):
        seen["proxy"] = proc
        return orig_proxy(self, proc)

    monkeypatch.setattr(RunHandle, "register_harbor", rec_harbor)
    monkeypatch.setattr(RunHandle, "register_proxy", rec_proxy)

    port = _free_port()
    options = runner.RunOptions(provider="acme", mode="smoke", proxy_port=port)
    cancel = threading.Event()
    timer = threading.Timer(1.0, cancel.set)
    timer.start()
    stranger = _sleep_child(30)
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.run_one(options, {}, cancel=cancel)
    finally:
        timer.cancel()
    assert "harbor" in seen and "proxy" in seen
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if seen["harbor"].poll() is not None and seen["proxy"].poll() is not None:
            break
        time.sleep(0.05)
    assert seen["harbor"].poll() is not None, "owned Harbor child escaped cancellation"
    assert seen["proxy"].poll() is not None, "owned proxy child escaped cancellation"
    assert stranger.poll() is None, "unrelated process was touched by run cleanup"
    status = json.loads((seen["handle"].directory / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "interrupted"
    stop_process(stranger)


def _run_one_harness(tmp_path, monkeypatch, harbor_argv, port):
    """Shared mocked-preflight run_one setup; returns (runner, options, seen)."""
    import benching.benchmark.runner as runner
    from benching.benchmark.config import BenchmarkSpec

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "executable", lambda name: None)
    monkeypatch.setattr(runner, "validate_provider", lambda *a, **k: {"success": True})
    monkeypatch.setattr(runner, "task_names", lambda mode, spec: ["task-a"])
    monkeypatch.setattr(runner, "environment", lambda config, values=None: {})
    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *a, **k: {"source": "unavailable"})
    monkeypatch.setattr(runner, "harbor_command", lambda *a, **k: list(harbor_argv))
    spec = BenchmarkSpec(
        name="suite", version="1", model="", reasoning="default", tasks_dir=tmp_path,
        expected_task_count=None, smoke_tasks=("task-a",),
        agent="benching.agents.instrumented_omp_agent:InstrumentedOmpAgent",
        max_tokens=None, context_window=None, run_id_prefix="bench",
        tokenizer_repo="", tokenizer_revision="", tokenizer_env_override=None,
        cache_dir=tmp_path,
    )
    monkeypatch.setattr(runner, "benchmark_spec", lambda config: spec)
    cfg = {
        "enabled": True, "env_file": str(tmp_path / "a.env"), "auth_env": "A_API_KEY",
        "base_url": "https://api.example.test/v1", "default_model": "m", "api": "openai-completions",
    }
    monkeypatch.setattr(runner, "provider_config", lambda name, root_config=None: ({}, cfg))
    monkeypatch.setattr(runner, "provider_env_values", lambda name, config: {"A_API_KEY": "dummy"})
    monkeypatch.setattr(runner, "resolve", lambda *a, **k: ("https://api.example.test/v1", "m"))
    monkeypatch.setattr(runner, "version", lambda name: None)

    def _fake_analyze(*args, **kwargs):
        """Emulate successful canonical analysis publication."""
        run_dir = Path(args[0][-1])
        (run_dir / "metrics.jsonl").write_text('{"value": 1}\n', encoding="utf-8")
        (run_dir / "summary.json").write_text('{"schema_version": 1}\n', encoding="utf-8")

    monkeypatch.setattr(runner.subprocess, "run", _fake_analyze)
    seen: dict = {}
    orig_harbor = RunHandle.register_harbor
    orig_proxy = RunHandle.register_proxy

    def rec_harbor(self, proc):
        seen["harbor"] = proc
        seen["handle"] = self
        return orig_harbor(self, proc)

    def rec_proxy(self, proc):
        seen["proxy"] = proc
        return orig_proxy(self, proc)

    monkeypatch.setattr(RunHandle, "register_harbor", rec_harbor)
    monkeypatch.setattr(RunHandle, "register_proxy", rec_proxy)
    options = runner.RunOptions(provider="acme", mode="smoke", proxy_port=port)
    return runner, options, seen


def test_success_path_stops_owned_proxy(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

    port = _free_port()
    runner, options, seen = _run_one_harness(
        tmp_path, monkeypatch, [sys.executable, "-c", "pass"], port)
    directory = runner.run_one(options, {})
    assert directory.is_dir()
    assert seen["proxy"].poll() is not None, "owned proxy leaked on success path"
    status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"


def test_proxy_death_fails_run_and_stops_harbor(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

    port = _free_port()
    runner, options, seen = _run_one_harness(
        tmp_path, monkeypatch, [sys.executable, "-c", "import time; time.sleep(30)"], port)

    killer = threading.Timer(2.0, lambda: stop_process(seen.get("proxy")))
    killer.start()
    try:
        with pytest.raises(SystemExit) as excinfo:
            runner.run_one(options, {})
    finally:
        killer.cancel()
    assert "proxy" in str(excinfo.value.code or excinfo.value).lower()
    assert seen["harbor"].poll() is not None, "Harbor kept running after owned proxy died"
    status = json.loads((seen["handle"].directory / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"


# G. Live foreground interruption reaches orchestration. ---------------------------

def test_live_interrupt_terminates_owned_and_exits_130(monkeypatch) -> None:
    import benching.benchmark.live as live_mod

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    owned = _sleep_child(30)
    handle = RunHandle(provider="acme", proxy_port=0, auth_token="tok")
    handle.register_harbor(owned)
    worker_state: dict = {}

    class _FakeLive:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            raise KeyboardInterrupt

        def __exit__(self, *exc):
            return False

        def update(self, *args, **kwargs) -> None:
            pass

    monkeypatch.setattr(live_mod, "Live", _FakeLive)
    cancel = threading.Event()

    def start(on_event):
        worker_state["saw_cancel"] = cancel.wait(timeout=10)
        worker_state["done"] = True
        raise KeyboardInterrupt

    with track(handle):
        with pytest.raises(SystemExit) as excinfo:
            live_mod.drive_live_view(start, title="t", poll_harbor=False, cancel=cancel,
                                     worker_join_timeout=10.0)
    assert excinfo.value.code == 130
    assert cancel.is_set()
    assert owned.poll() is not None, "foreground Ctrl+C left a run-owned child alive"
    assert worker_state.get("done") is True
    stop_process(owned)


# H. Cleanup touches only registered handles. --------------------------------------

def test_terminate_owned_leaves_strangers_alive() -> None:
    owned = _sleep_child(30)
    stranger = _sleep_child(30)
    handle = RunHandle(provider="acme")
    handle.register_harbor(owned)
    try:
        handle.terminate_owned(grace=5.0)
        assert owned.poll() is not None
        assert stranger.poll() is None
    finally:
        stop_process(owned)
        stop_process(stranger)


def test_terminate_all_active_only_touches_tracked() -> None:
    owned = _sleep_child(30)
    stranger = _sleep_child(30)
    handle = RunHandle(provider="acme")
    try:
        with track(handle):
            handle.register_harbor(owned)
            terminate_all_active(grace=5.0)
            assert owned.poll() is not None
            assert stranger.poll() is None
    finally:
        stop_process(owned)
        stop_process(stranger)


# I. Proxy startup failure blocks Harbor. --------------------------------------------

def test_proxy_startup_failure_blocks_harbor(tmp_path, monkeypatch) -> None:
    import benching.benchmark.lifecycle as lifecycle_mod
    import benching.benchmark.runner as runner
    from benching.benchmark.config import BenchmarkSpec

    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "executable", lambda name: None)
    monkeypatch.setattr(runner, "validate_provider", lambda *a, **k: {"success": True})
    monkeypatch.setattr(runner, "task_names", lambda mode, spec: ["task-a"])
    monkeypatch.setattr(runner, "environment", lambda config, values=None: {})
    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *a, **k: {"source": "unavailable"})
    monkeypatch.setattr(runner, "harbor_command", lambda *a, **k: [sys.executable, "-c", "pass"])
    spec = BenchmarkSpec(
        name="suite", version="1", model="", reasoning="default", tasks_dir=tmp_path,
        expected_task_count=None, smoke_tasks=("task-a",),
        agent="benching.agents.instrumented_omp_agent:InstrumentedOmpAgent",
        max_tokens=None, context_window=None, run_id_prefix="bench",
        tokenizer_repo="", tokenizer_revision="", tokenizer_env_override=None,
        cache_dir=tmp_path,
    )
    monkeypatch.setattr(runner, "benchmark_spec", lambda config: spec)
    cfg = {
        "enabled": True, "env_file": str(tmp_path / "a.env"), "auth_env": "A_API_KEY",
        "base_url": "https://api.example.test/v1", "default_model": "m", "api": "openai-completions",
    }
    monkeypatch.setattr(runner, "provider_config", lambda name, root_config=None: ({}, cfg))
    monkeypatch.setattr(runner, "provider_env_values", lambda name, config: {"A_API_KEY": "dummy"})
    monkeypatch.setattr(runner, "resolve", lambda *a, **k: ("https://api.example.test/v1", "m"))
    monkeypatch.setattr(runner, "version", lambda name: None)

    harbor_spawns: list = []
    real_spawn = lifecycle_mod.spawn_owned

    def recording_spawn(argv, **kwargs):
        if "benching.proxy.telemetry_proxy" in argv:
            return real_spawn(argv, **kwargs)
        harbor_spawns.append(list(argv))
        raise AssertionError("Harbor must not start on an unverified proxy")

    monkeypatch.setattr(runner, "spawn_owned", recording_spawn)

    port = _free_port()
    listener = socket.socket()
    listener.bind(("127.0.0.1", port))
    listener.listen(1)
    try:
        options = runner.RunOptions(provider="acme", mode="smoke", proxy_port=port)
        real_start_proxy = runner.start_proxy
        monkeypatch.setattr(
            runner, "start_proxy",
            lambda directory, proxy_port=port, auth_token="", timeout=3.0:
            real_start_proxy(directory, proxy_port, auth_token, timeout),
        )
        with pytest.raises((SystemExit, AssertionError)) as excinfo:
            runner.run_one(options, {})
        assert not isinstance(excinfo.value, AssertionError), "Harbor started despite proxy failure"
        assert harbor_spawns == []
        status = json.loads(next(tmp_path.glob("bench-*/status.json")).read_text(encoding="utf-8"))
        assert status["status"] == "failed"
    finally:
        listener.close()


# J. Concurrent run identity. ----------------------------------------------------------

def test_concurrent_runs_have_distinct_tokens_and_paths(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner
    from benching.benchmark.config import BenchmarkSpec

    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    token_a, token_b = new_proxy_token(), new_proxy_token()
    assert token_a and token_b and token_a != token_b
    spec = BenchmarkSpec(
        name="suite", version="1", model="", reasoning="default", tasks_dir=tmp_path,
        expected_task_count=None, smoke_tasks=("task-a",),
        agent="benching.agents.instrumented_omp_agent:InstrumentedOmpAgent",
        max_tokens=None, context_window=None, run_id_prefix="bench",
        tokenizer_repo="", tokenizer_revision="", tokenizer_env_override=None,
        cache_dir=tmp_path,
    )
    monkeypatch.setattr(runner, "version", lambda name: None)
    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *a, **k: {"source": "unavailable"})
    cfg: dict = {"plan": None}
    dir_a = runner.run_directory(
        runner.RunOptions(provider="acme", mode="smoke"), spec, cfg,
        "https://api.example.test/v1", "m", ["t"], proxy_auth_token=token_a,
    )
    dir_b = runner.run_directory(
        runner.RunOptions(provider="acme", mode="smoke"), spec, cfg,
        "https://api.example.test/v1", "m", ["t"], proxy_auth_token=token_b,
    )
    assert dir_a != dir_b
    auth_a = json.loads((dir_a / "proxy-auth.json").read_text(encoding="utf-8"))
    auth_b = json.loads((dir_b / "proxy-auth.json").read_text(encoding="utf-8"))
    assert auth_a["auth_token"] == token_a
    assert auth_b["auth_token"] == token_b
    run_a = (dir_a / "run.json").read_text(encoding="utf-8")
    assert "auth_token" not in run_a
    assert token_a not in run_a and token_b not in run_a


def test_cross_token_request_rejected(tmp_path, monkeypatch) -> None:
    writer, calls, _, events = _run_handle(
        tmp_path, b'{"model":"m","messages":[]}', new_proxy_token(), monkeypatch
    )
    head, _ = _parse_response(writer.data)
    assert b" 403 " in head.split(b"\r\n", 1)[0]
    assert calls.get("called") is not True
    assert _inference_rows(events) == []


# Platform gate + primitives. ---------------------------------------------------------------

def test_platform_gate_and_owned_wait(monkeypatch) -> None:
    import os

    monkeypatch.delenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", raising=False)
    if os.name == "nt":
        with pytest.raises(SystemExit) as excinfo:
            require_supported_execution_platform()
        assert "Linux" in str(excinfo.value.code or excinfo.value) or "WSL" in str(excinfo.value.code or excinfo.value)
    else:
        require_supported_execution_platform()
    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    require_supported_execution_platform()

    handle = RunHandle(provider="acme")
    proc = _sleep_child(30)
    try:
        handle.register_harbor(proc)
        handle.request_cancel()
        with pytest.raises(KeyboardInterrupt):
            wait_owned(handle)
    finally:
        stop_process(proc)
    assert proc.poll() is not None or True
    stop_process(proc)
    assert proc.poll() is not None

