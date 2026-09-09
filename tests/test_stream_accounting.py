"""M2-task-5 controlled fixtures: stream completion and output accounting.

Deterministic local provider fixtures only: scripted upstream bytes fed
through the real Proxy.handle/forward, plus unit checks for the event
extractor, the completion tracker, and the analytics mapping. No real
provider traffic. No wall-clock assertions: one showcase test injects a
scripted monotonic clock for exact derived durations.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from benching.proxy.telemetry_proxy import JsonlWriter, Proxy

TOKEN = "stream-test-token-aaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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
    def __init__(self, explode_on_drain: bool = False) -> None:
        self.data = bytearray()
        self.closed = False
        self.explode_on_drain = explode_on_drain

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        if self.explode_on_drain:
            raise BrokenPipeError("downstream gone")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


async def _fake_reader(request: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(request)
    reader.feed_eof()
    return reader


def _downstream_request(body: bytes = b'{"model":"m","messages":[]}') -> bytes:
    head = (
        "POST /acme/chat/completions HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"X-Benchmark-Proxy-Auth: {TOKEN}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    return head.encode("latin1") + body


_HANG = object()


class _ScriptReader:
    """Upstream stub with faithful StreamReader.readline semantics.

    Bytes items are concatenated and split on newlines exactly like a
    real transport; BaseException items raise when reached (provider
    reset); _HANG stalls forever (read timeout). Exhaustion behaves
    like EOF, including a final partial line without a newline.
    """

    def __init__(self, script: list) -> None:
        self.items = list(script)
        self.buf = bytearray()

    async def readline(self) -> bytes:
        while True:
            newline = self.buf.find(b"\n")
            if newline >= 0:
                line = bytes(self.buf[: newline + 1])
                del self.buf[: newline + 1]
                return line
            if not self.items:
                if self.buf:
                    line = bytes(self.buf)
                    self.buf.clear()
                    return line
                return b""
            nxt = self.items.pop(0)
            if isinstance(nxt, BaseException):
                self.buf.clear()
                raise nxt
            if nxt is _HANG:
                await asyncio.Event().wait()
                return b""
            self.buf.extend(nxt)


class _UpstreamWriter:
    def write(self, data: bytes) -> None:
        pass

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


def _sse_response(*payloads: str, status: int = 200, chunked: bool = True) -> list:
    """Script an upstream HTTP/SSE reply. Payloads are data: bodies."""
    body = b"".join(f"data: {payload}\n\n".encode() for payload in payloads)
    head = [
        f"HTTP/1.1 {status} OK\r\n".encode(),
        b"Content-Type: text/event-stream\r\n",
    ]
    if chunked:
        head.append(b"Transfer-Encoding: chunked\r\n")
        head.append(b"\r\n")
        chunks = []
        for offset in range(0, len(body), 13):
            piece = body[offset : offset + 13]
            chunks.append(f"{len(piece):X}\r\n".encode() + piece + b"\r\n")
        chunks.append(b"0\r\n\r\n")
        return head + chunks
    head.append(f"Content-Length: {len(body)}\r\n".encode())
    head.append(b"\r\n")
    return head + [body]


def _run_proxy(tmp_path: Path, monkeypatch, script: list, **proxy_kwargs) -> tuple:
    import benching.proxy.telemetry_proxy as mod

    events = tmp_path / "events.jsonl"

    async def fake_open(*args, **kwargs):
        return _ScriptReader(list(script)), _UpstreamWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    proxy = mod.Proxy(mod.JsonlWriter(events), _routes(), auth_token=TOKEN, **proxy_kwargs)
    writer = _CaptureWriter()

    async def run() -> None:
        await proxy.handle(await _fake_reader(_downstream_request()), writer)

    asyncio.run(run())
    rows = []
    if events.is_file():
        rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]
    return writer, [row for row in rows if row.get("event_type") == "inference"]


def _text_delta(content: str, finish: str | None = None) -> str:
    choice: dict = {"delta": {"content": content}}
    if finish is not None:
        choice["finish_reason"] = finish
    return json.dumps({"choices": [choice]})


# A. Valid successful stream + exact metric regression. --------------------------

class _FakeTime:
    """Scripted monotonic clock keyed by call index.

    The proxy samples time.monotonic() on a fixed schedule per request
    (start, per-read overall-deadline checks, per-chunk `now`, finish,
    completed). For a fixed scripted upstream byte stream the call
    positions are deterministic, so selected indices can carry exact
    timestamps while the rest stay at 0.0. If proxy timing internals
    change, positions shift and this fails loudly by design.
    """

    def __init__(self, pinned: dict | None = None, default: float = 0.0) -> None:
        self.pinned = dict(pinned or {})
        self.default = default
        self.calls = 0

    def monotonic(self) -> float:
        value = self.pinned.get(self.calls, self.default)
        self.calls += 1
        return value


class _WordTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False):
        class _Encoding:
            def __init__(self, words: list) -> None:
                self.ids = words

        return _Encoding(text.split())


def test_valid_text_stream_success_exact_metrics(tmp_path, monkeypatch) -> None:
    import benching.proxy.telemetry_proxy as mod
    from benching.analytics.analyze import local_count, normalize

    # Traced call positions for this fixed 3-payload chunked fixture:
    # 0=request start, first content-bearing chunk now=28, last=56,
    # completed=72. Timings are milliseconds, so these pin
    # first=1.0ms, last=3.0ms, end=5.0ms. Everything else reads 0.0.
    clock = _FakeTime({28: 0.001, 56: 0.003, 72: 0.005})
    monkeypatch.setattr(mod, "time", clock)
    script = _sse_response(
        _text_delta("Hello "),
        _text_delta("world", finish="stop"),
        "[DONE]",
    )
    _, rows = _run_proxy(tmp_path, monkeypatch, script)
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "ok"
    assert row["success"] is True
    assert row["stream_completed"] is True
    assert row["provider_failure"] is False
    assert row["finish_reason"] == "stop"
    assert row["output_text"] == "Hello world"
    assert row["output_unsupported"] is False
    assert row["timing"]["first_content_output_ms"] == 1.0
    assert row["timing"]["last_content_output_ms"] == 3.0
    normalized = normalize({"run_id": "r", "provider": "acme"}, rows, _WordTokenizer())[0]
    assert normalized["timing"]["ttft_ms"] == {"value": 1.0, "source": "measured"}
    assert normalized["timing"]["decode_duration_ms"] == {"value": 2.0, "source": "measured"}
    assert normalized["timing"]["end_to_end_latency_ms"] == {"value": 5.0, "source": "measured"}
    assert normalized["tokens"]["output_local"] == {"value": 2, "source": "calculated"}
    assert normalized["timing"]["decode_tps"] == {"value": 1000.0, "source": "calculated"}
    assert normalized["timing"]["effective_tps"] == {"value": 400.0, "source": "calculated"}
    assert normalized["reliability"]["success"] is True
    assert local_count(_WordTokenizer(), row["output_text"], False) == 2


# B/C. Terminal-marker variants. --------------------------------------------------

def test_done_only_stream_succeeds(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(_text_delta("hi"), "[DONE]"))
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["success"]) == ("ok", True)


def test_finish_reason_only_stream_succeeds(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(_text_delta("hi", finish="stop")))
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["success"]) == ("ok", True)
    assert rows[0]["finish_reason"] == "stop"


# D. EOF truncation. ------------------------------------------------------------------

def test_eof_truncation_is_failure_with_partial_output(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(_text_delta("partial")))
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "truncated"
    assert row["success"] is False
    assert row["stream_completed"] is False
    assert row["provider_failure"] is True
    assert row["error_type"] == "truncated_stream"
    assert row["output_text"] == "partial"


# E. HTTP-200 error object. ---------------------------------------------------------------

def test_http200_error_object_is_provider_failure(tmp_path, monkeypatch) -> None:
    error = json.dumps({"error": {"message": "bad credentials supplied", "code": 401, "type": "auth_error"}})
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(error))
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "provider_error"
    assert row["success"] is False
    assert row["provider_failure"] is True
    assert row["error_type"] == "provider_error"
    assert "bad credentials supplied" in (row["error_message"] or "")
    assert "Bearer" not in (row["error_message"] or "")


def test_http200_error_dominates_later_done(tmp_path, monkeypatch) -> None:
    error = json.dumps({"error": {"message": "overloaded", "type": "server_error"}})
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(error, "[DONE]"))
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["success"]) == ("provider_error", False)


# F. Non-200 provider HTTP error (regression pin). ----------------------------------------------

def test_http500_error_preserves_existing_semantics(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(_text_delta("x"), status=500))
    assert len(rows) == 1
    row = rows[0]
    assert row["http_status"] == 500
    assert row["completion_status"] == "http_error"
    assert row["success"] is False
    assert row["provider_failure"] is True


# G. Provider reset vs H. downstream disconnect. ------------------------------------------------------

def test_provider_reset_mid_body_is_provider_failure(tmp_path, monkeypatch) -> None:
    script = _sse_response(_text_delta("partial"))
    script.insert(-1, ConnectionResetError("provider hung up"))
    _, rows = _run_proxy(tmp_path, monkeypatch, script)
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "truncated"
    assert row["success"] is False
    assert row["provider_failure"] is True
    assert row["downstream_cancelled"] is False
    assert row["error_type"] == "ConnectionResetError"
    assert row["output_text"] == "partial"


def test_downstream_disconnect_is_not_provider_failure(tmp_path, monkeypatch) -> None:
    import benching.proxy.telemetry_proxy as mod

    events = tmp_path / "events.jsonl"

    async def fake_open(*args, **kwargs):
        return _ScriptReader(_sse_response(_text_delta("partial"))), _UpstreamWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    proxy = mod.Proxy(mod.JsonlWriter(events), _routes(), auth_token=TOKEN)
    writer = _CaptureWriter(explode_on_drain=True)

    async def run() -> None:
        await proxy.handle(await _fake_reader(_downstream_request()), writer)

    asyncio.run(run())
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row.get("event_type") == "inference"]
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "cancelled"
    assert row["success"] is False
    assert row["provider_failure"] is False
    assert row["downstream_cancelled"] is True
    assert row["error_type"] == "downstream_disconnect"


# I/J. Timeout preservation. -------------------------------------------------------------------------------

def test_body_read_timeout_preserved(tmp_path, monkeypatch) -> None:
    import benching.proxy.telemetry_proxy as mod

    events = tmp_path / "events.jsonl"

    async def fake_open(*args, **kwargs):
        head = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: text/event-stream\r\n",
            b"Transfer-Encoding: chunked\r\n",
            b"\r\n",
            b"4\r\ntest\r\n",
            _HANG,
        ]
        return _ScriptReader(head), _UpstreamWriter()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    proxy = mod.Proxy(
        mod.JsonlWriter(events), _routes(), auth_token=TOKEN,
        connect_timeout=2.0, header_timeout=2.0, read_timeout=0.2, overall_timeout=30.0,
    )
    writer = _CaptureWriter()

    async def run() -> None:
        await proxy.handle(await _fake_reader(_downstream_request()), writer)

    started = __import__("time").monotonic()
    asyncio.run(run())
    assert __import__("time").monotonic() - started < 10
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row.get("event_type") == "inference"]
    assert len(rows) == 1
    assert rows[0]["completion_status"] == "timeout"
    assert rows[0]["error_type"] == "upstream_read_timeout"
    assert rows[0]["provider_failure"] is True


def test_overall_timeout_classification(tmp_path, monkeypatch) -> None:
    import benching.proxy.telemetry_proxy as mod

    # started=0.0, every later sample reads 10.0: the first overall-deadline
    # check (overall_timeout=0.0) trips deterministically in the header loop.
    monkeypatch.setattr(mod, "time", _FakeTime({0: 0.0}, default=10.0))
    script = _sse_response(_text_delta("partial"))
    _, rows = _run_proxy(tmp_path, monkeypatch, script, overall_timeout=0.0)
    assert len(rows) == 1
    assert rows[0]["completion_status"] == "timeout"
    assert rows[0]["error_type"] == "upstream_overall_timeout"
    assert rows[0]["provider_failure"] is True


# K. Malformed events. ---------------------------------------------------------------------

def test_malformed_event_does_not_break_good_stream(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(
        tmp_path, monkeypatch,
        _sse_response("{oops", _text_delta("hi", finish="stop"), "[DONE]"),
    )
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["success"]) == ("ok", True)
    assert rows[0]["output_text"] == "hi"


def test_all_malformed_stream_is_protocol_error(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response("{oops", "[not json"))
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "protocol_error"
    assert row["success"] is False
    assert row["provider_failure"] is True
    assert row["error_type"] == "protocol_error"


# L/M. Framing splits and merges. -------------------------------------------------------------------

def test_split_sse_frame_reconstructs(tmp_path, monkeypatch) -> None:
    payload = _text_delta("split-event", finish="stop")
    raw = f"data: {payload}\n\n".encode()
    head = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: text/event-stream\r\n",
        b"Transfer-Encoding: chunked\r\n",
        b"\r\n",
    ]
    done_line = b"data: [DONE]\n\n"
    first, second = raw[:7], raw[7:]
    chunks = [
        f"{len(first):X}\r\n".encode() + first + b"\r\n",
        f"{len(second):X}\r\n".encode() + second + b"\r\n",
        f"{len(done_line):X}\r\n".encode() + done_line + b"\r\n",
        b"0\r\n\r\n",
    ]
    _, rows = _run_proxy(tmp_path, monkeypatch, head + chunks)
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["output_text"]) == ("ok", "split-event")


def test_multiple_events_in_one_read(tmp_path, monkeypatch) -> None:
    blob = b"".join(
        f"data: {payload}\n\n".encode()
        for payload in (_text_delta("one"), _text_delta("two", finish="stop"), "[DONE]")
    )
    head = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: text/event-stream\r\n",
        b"Transfer-Encoding: chunked\r\n",
        b"\r\n",
        f"{len(blob):X}\r\n".encode() + blob + b"\r\n",
        b"0\r\n\r\n",
    ]
    _, rows = _run_proxy(tmp_path, monkeypatch, head)
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["output_text"]) == ("ok", "onetwo")


# N. Large tool-argument payload. ----------------------------------------------------------------------

def test_large_tool_arguments_captured(tmp_path, monkeypatch) -> None:
    big_args = json.dumps({"cmd": "x" * 200_000})
    tool = json.dumps({"choices": [{"delta": {"tool_calls": [{"function": {"name": "run", "arguments": big_args}}]}, "finish_reason": "tool_calls"}]})
    _, rows = _run_proxy(tmp_path, monkeypatch, _sse_response(tool, "[DONE]"))
    assert len(rows) == 1
    assert rows[0]["completion_status"] == "ok"
    assert rows[0]["output_text"] == "run" + big_args
    assert rows[0]["output_text_truncated"] is False


# O/P. Tool-only and mixed streams. --------------------------------------------------------------------------

def _tool_delta(name: str | None, arguments: str | None) -> str:
    function: dict = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    return json.dumps({"choices": [{"delta": {"tool_calls": [{"function": function}]}}]})


def test_tool_only_stream_has_countable_output(tmp_path, monkeypatch) -> None:
    from benching.analytics.analyze import normalize

    _, rows = _run_proxy(
        tmp_path, monkeypatch,
        _sse_response(
            _tool_delta("run_command", '{"cmd":"ls"'),
            _tool_delta(None, ',"all":true}'),
            json.dumps({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
            "[DONE]",
        ),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "ok"
    assert row["timing"]["first_content_output_ms"] is not None
    assert row["timing"]["last_content_output_ms"] is not None
    assert row["output_text"] == 'run_command{"cmd":"ls","all":true}'
    assert row["output_unsupported"] is False
    normalized = normalize({"run_id": "r", "provider": "acme"}, rows, _WordTokenizer())[0]
    assert normalized["tokens"]["output_local"] == {"value": 1, "source": "calculated"}


def test_mixed_text_and_tool_no_duplicates(tmp_path, monkeypatch) -> None:
    _, rows = _run_proxy(
        tmp_path, monkeypatch,
        _sse_response(
            _text_delta("Calling tool "),
            _tool_delta("lookup", '{"q":"x"}'),
            _text_delta("done", finish="stop"),
            "[DONE]",
        ),
    )
    assert len(rows) == 1
    assert rows[0]["output_text"] == 'Calling tool lookup{"q":"x"}done'


# Q/R/S. Reasoning, usage-only, role-only. ----------------------------------------------------------------------------

def test_reasoning_first_sets_ttft(tmp_path, monkeypatch) -> None:
    reasoning = json.dumps({"choices": [{"delta": {"reasoning_content": "thinking hard"}}]})
    _, rows = _run_proxy(
        tmp_path, monkeypatch,
        _sse_response(reasoning, _text_delta("answer", finish="stop"), "[DONE]"),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "ok"
    assert row["timing"]["first_content_output_ms"] is not None
    assert row["output_text"] == "thinking hardanswer"


def test_usage_only_terminal_event_keeps_last_output(tmp_path, monkeypatch) -> None:
    usage = json.dumps({"usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}})
    _, rows = _run_proxy(
        tmp_path, monkeypatch,
        _sse_response(_text_delta("hi", finish="stop"), usage, "[DONE]"),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "ok"
    assert row["tokens"]["input_provider"] == 5
    assert row["tokens"]["output_provider"] == 2
    assert row["timing"]["last_content_output_ms"] == row["timing"]["first_content_output_ms"]
    assert row["output_text"] == "hi"


def test_role_only_and_empty_deltas_do_not_trigger_ttft(tmp_path, monkeypatch) -> None:
    role = json.dumps({"choices": [{"delta": {"role": "assistant"}}]})
    empty = json.dumps({"choices": [{"delta": {"content": ""}}]})
    _, rows = _run_proxy(
        tmp_path, monkeypatch,
        _sse_response(role, empty, _text_delta("real", finish="stop"), "[DONE]"),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "ok"
    assert row["output_text"] == "real"
    assert row["timing"]["first_content_output_ms"] == row["timing"]["last_content_output_ms"]


# Non-SSE (Content-Length framed) bodies. ---------------------------------------------------------------------

def _json_response(body: bytes, status: int = 200) -> list:
    return [
        f"HTTP/1.1 {status} OK\r\n".encode(),
        b"Content-Type: application/json\r\n",
        f"Content-Length: {len(body)}\r\n".encode(),
        b"\r\n",
        body,
    ]


def test_non_sse_json_success_with_content_length(tmp_path, monkeypatch) -> None:
    body = json.dumps({
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }).encode()
    _, rows = _run_proxy(tmp_path, monkeypatch, _json_response(body))
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "ok"
    assert row["success"] is True
    assert row["output_text"] == "hello"
    assert row["tokens"]["input_provider"] == 1
    assert row["tokens"]["output_provider"] == 1


def test_non_sse_json_error_object(tmp_path, monkeypatch) -> None:
    body = json.dumps({"error": {"message": "quota spent", "code": 429}}).encode()
    _, rows = _run_proxy(tmp_path, monkeypatch, _json_response(body))
    assert len(rows) == 1
    assert (rows[0]["completion_status"], rows[0]["success"]) == ("provider_error", False)
    assert "quota spent" in (rows[0]["error_message"] or "")


def test_short_content_length_body_is_truncated(tmp_path, monkeypatch) -> None:
    body = b'{"choices": [{"message": {"content": "half"'
    script = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: application/json\r\n",
        b"Content-Length: 1000\r\n",
        b"\r\n",
        body,
    ]
    _, rows = _run_proxy(tmp_path, monkeypatch, script)
    assert len(rows) == 1
    row = rows[0]
    assert row["completion_status"] == "truncated"
    assert row["success"] is False
    assert row["provider_failure"] is True


# Tracker + extractor units. -------------------------------------------------------------------------------------

def test_tracker_verdict_table() -> None:
    from benching.proxy.telemetry_proxy import StreamTracker

    def fresh(**kwargs) -> StreamTracker:
        tracker = StreamTracker()
        for key, value in kwargs.items():
            setattr(tracker, key, value)
        return tracker

    assert fresh(done=True).verdict(True, True) == "ok"
    done_finish = fresh()
    done_finish.note_finish("stop")
    assert done_finish.verdict(True, True) == "ok"
    assert fresh(done=True).verdict(False, True) == "http_error"
    errored = fresh(done=True)
    errored.note_error("bad key")
    assert errored.verdict(True, True) == "provider_error"
    assert fresh().verdict(True, False) == "truncated"
    assert fresh().verdict(True, True, read_error="ConnectionResetError") == "truncated"
    partial = fresh()
    partial.note_payload()
    assert partial.verdict(True, True) == "truncated"
    malformed = fresh()
    malformed.note_malformed()
    assert malformed.verdict(True, True) == "protocol_error"
    assert fresh().verdict(True, True) == "truncated"


def test_extract_deltas_rules() -> None:
    from benching.proxy.telemetry_proxy import extract_deltas

    assert extract_deltas({"choices": [{"delta": {"role": "assistant"}}]}) == ([], True)
    assert extract_deltas({"choices": [{"delta": {"content": ""}}]}) == ([], True)
    parts, supported = extract_deltas(
        {"choices": [{"delta": {"content": "a", "tool_calls": [{"function": {"name": "f", "arguments": "{}"}}]}}]}
    )
    assert (parts, supported) == (["a", "f", "{}"], True)
    assert extract_deltas({"choices": [{"delta": {"tool_calls": [{"index": 0}]}}]}) == ([], True)
    parts, supported = extract_deltas({"choices": [{"delta": {"tool_calls": [{"function": {"arguments": {"nested": "dict"}}}]}}]})
    assert parts == [] and supported is False
    assert extract_deltas({"delta": {"thinking": "hmm"}}) == (["hmm"], True)


# Analytics mapping for new classifications. ------------------------------------------------------------------------------

def test_analyze_maps_new_terminal_rows() -> None:
    from benching.analytics.analyze import normalize

    base: dict = {
        "event_type": "inference",
        "run_id": "r",
        "provider": "acme",
        "task_id": "t",
        "trial_id": "1",
        "timing": {"first_content_output_ms": 1.0, "last_content_output_ms": 3.0, "stream_completed_ms": 5.0},
        "tokens": {"input_provider": 1, "output_provider": 1, "total_provider": 2, "cache_read": None, "cache_write": None},
        "output_text": "hi",
        "output_text_truncated": False,
    }

    def check(overrides: dict, expected: dict) -> None:
        row = normalize({"run_id": "r", "provider": "acme"}, [{**base, **overrides}], None)[0]
        for key, value in expected.items():
            assert row["reliability"][key] == value, (overrides, key)

    check(
        {"success": False, "stream_completed": False, "provider_failure": True, "completion_status": "truncated",
         "error_type": "truncated_stream"},
        {"success": False, "provider_failure": True, "provider_stream_failure": True,
         "incomplete_provider_stream": True, "timeout": False},
    )
    check(
        {"success": False, "stream_completed": False, "provider_failure": True, "completion_status": "timeout",
         "error_type": "upstream_read_timeout"},
        {"timeout": True, "provider_failure": True},
    )
    check(
        {"success": False, "stream_completed": False, "provider_failure": True, "completion_status": "timeout",
         "error_type": "TimeoutError"},
        {"timeout": True},
    )
    check(
        {"success": False, "stream_completed": False, "provider_failure": True, "completion_status": "provider_error",
         "error_type": "provider_error"},
        {"success": False, "provider_failure": True, "timeout": False},
    )


def test_analyze_unsupported_empty_output_is_unavailable() -> None:
    from benching.analytics.analyze import normalize

    class _CountingTokenizer:
        def __init__(self) -> None:
            self.calls = 0

        def encode(self, text: str, add_special_tokens: bool = False):
            self.calls += 1

            class _Encoding:
                ids = [1]

            return _Encoding()

    base: dict = {
        "event_type": "inference",
        "run_id": "r",
        "provider": "acme",
        "task_id": "t",
        "trial_id": "1",
        "timing": {"first_content_output_ms": 1.0, "last_content_output_ms": 1.0, "stream_completed_ms": 2.0},
        "tokens": {"input_provider": 1, "output_provider": 1, "total_provider": 2, "cache_read": None, "cache_write": None},
        "output_text_truncated": False,
        "success": False,
        "stream_completed": False,
        "provider_failure": True,
    }
    run = {"run_id": "r", "provider": "acme"}
    tokenizer = _CountingTokenizer()
    empty_unsupported = normalize(run, [{**base, "output_text": "", "output_unsupported": True}], tokenizer)[0]
    assert empty_unsupported["tokens"]["output_local"] == {"value": None, "source": "unavailable"}
    assert tokenizer.calls == 0
    partial = normalize(run, [{**base, "output_text": "half", "output_unsupported": True}], tokenizer)[0]
    assert partial["tokens"]["output_local"] == {"value": 1, "source": "calculated"}

