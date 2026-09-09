#!/usr/bin/env python3
"""Transparent OpenAI-compatible streaming proxy with per-run JSONL telemetry."""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import signal
import time
import uuid
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from benching.benchmark._util import redact, utc

MAX_REQUEST_LINE = 16 * 1024
MAX_HEADERS = 128 * 1024
MAX_BODY = 32 * 1024 * 1024
MAX_CAPTURE = 32 * 1024 * 1024
BENCHMARK_HEADERS = {
    "x-benchmark-provider",
    "x-benchmark-upstream",
    "x-benchmark-run-id",
    "x-benchmark-task",
    "x-benchmark-trial",
    "x-benchmark-agent-invocation-id",
    "x-benchmark-proxy-auth",
}
PROXY_AUTH_HEADER = "x-benchmark-proxy-auth"
HEALTH_PATH = "/__benching_health"
# Bounded transport deadlines (seconds). Conservative: connection and header
# waits are short, per-read inactivity covers slow streams, and the overall
# cap bounds a single proxied request lifetime. No retries: a retry would
# change the experiment.
UPSTREAM_CONNECT_TIMEOUT = 10.0
UPSTREAM_HEADER_TIMEOUT = 30.0
UPSTREAM_READ_TIMEOUT = 120.0
UPSTREAM_OVERALL_TIMEOUT = 600.0
DOWNSTREAM_WRITE_TIMEOUT = 30.0
SERVER_SHUTDOWN_TIMEOUT = 10.0


class _DownstreamError(ValueError):
    """Malformed client request framing/body: 400-class, never a provider failure."""


class _UpstreamTimeout(TimeoutError):
    """Upstream stage deadline exceeded; carries the stage name."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"upstream {stage} timed out")
        self.stage = stage


class _DownstreamGone(Exception):
    """Downstream write failed mid-stream: client-side failure, not provider."""


class _NoUpstreamResponse(Exception):
    """Upstream closed/reset before any status line: no verdict possible."""

    def __init__(self, read_error: str | None) -> None:
        super().__init__("upstream closed without a response")
        self.read_error = read_error


def _tool_call_parts(entry: Any) -> tuple[list[str], bool]:
    """Extract countable text from one streamed tool-call entry.

    Returns (parts, supported). Supported shapes mirror OpenAI-compatible
    streaming: ``function.name`` / ``function.arguments`` strings (or the
    same keys at top level when no ``function`` object exists), or a plain
    string. Entries carrying only protocol metadata (index/id/type with no
    name or arguments) contribute nothing but are supported. Anything else
    non-empty is unsupported: it cannot be safely normalized into
    countable text.
    """
    if isinstance(entry, str):
        return ([entry] if entry else [], True)
    if not isinstance(entry, dict):
        return ([], entry in (None, "", [], {}))
    function = entry.get("function")
    source = function if isinstance(function, dict) else entry
    parts: list[str] = []
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = entry.get("name")
        arguments = entry.get("arguments")
    if isinstance(name, str) and name:
        parts.append(name)
    if isinstance(arguments, str) and arguments:
        parts.append(arguments)
    if parts:
        return (parts, True)
    if isinstance(source, dict) and any(
        key not in {"index", "id", "type", "function", "name", "arguments"} or (
            key in {"function", "name", "arguments"} and value not in (None, "", [], {})
        )
        for key, value in source.items()
    ):
        return ([], False)
    return ([], True)


def extract_deltas(event: dict[str, Any]) -> tuple[list[str], bool]:
    """Extract countable semantic output text from one stream event.

    Documented rule, in fixed order: visible text, then reasoning text,
    then tool-call names/arguments, then provider-specific text deltas.
    Empty strings, role-only deltas, and metadata-only tool entries yield
    no parts. Returns (parts, supported); ``supported`` is False when an
    uninterpretable tool/reasoning shape was present. Raw event bytes are
    never serialized: only these explicit fields count.
    """
    parts: list[str] = []
    supported = True

    def take(value: Any) -> None:
        if isinstance(value, str) and value:
            parts.append(value)

    choices = event.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                delta = {}
            message = choice.get("message")
            if not isinstance(message, dict):
                message = {}
            take(delta.get("content"))
            take(delta.get("text"))
            take(message.get("content"))
            for key in ("reasoning_content", "reasoning"):
                take(delta.get(key))
                take(message.get(key))
            for field in ("delta", "message"):
                calls = (delta if field == "delta" else message).get("tool_calls")
                if not isinstance(calls, list):
                    continue
                for entry in calls:
                    entry_parts, entry_supported = _tool_call_parts(entry)
                    parts.extend(entry_parts)
                    supported = supported and entry_supported
    delta = event.get("delta")
    if isinstance(delta, dict):
        take(delta.get("text"))
        take(delta.get("thinking"))
        take(delta.get("partial_json"))
        for calls in (delta.get("tool_calls"),):
            if not isinstance(calls, list):
                continue
            for entry in calls:
                entry_parts, entry_supported = _tool_call_parts(entry)
                parts.extend(entry_parts)
                supported = supported and entry_supported
    if event.get("type") in {"content_block_delta", "content_block_start"}:
        block = event.get("content_block")
        if isinstance(block, dict):
            take(block.get("text"))
    return parts, supported


def provider_error_detail(event: dict[str, Any]) -> str | None:
    """Redacted detail for an HTTP-200 provider error object, if present."""
    error = event.get("error")
    if error is None:
        return None
    if isinstance(error, str):
        return redact(error[:500]) or "provider error"
    if isinstance(error, dict):
        bits = []
        for key in ("type", "code", "message"):
            value = error.get(key)
            if isinstance(value, bool) or value is None:
                continue
            text = str(value).strip()
            if text:
                bits.append(text)
        detail = ": ".join(bits)[:500]
        return redact(detail) or "provider error"
    return "provider error"


class StreamTracker:
    """Explicit completion state for one forwarded SSE/JSON stream.

    EOF alone never proves success: a request is successful only with a
    supported terminal condition (``[DONE]``, a finish/stop reason, or —
    for non-SSE bodies — parsed semantic content) and no provider error.
    """

    def __init__(self) -> None:
        self.events = 0
        self.malformed = 0
        self.done = False
        self.finish_reason: str | None = None
        self.error_detail: str | None = None
        self.unsupported_shape = False

    def note_payload(self) -> None:
        self.events += 1

    def note_malformed(self) -> None:
        self.malformed += 1

    def note_done(self) -> None:
        self.events += 1
        self.done = True

    def note_finish(self, reason: Any) -> None:
        if reason is not None:
            self.finish_reason = str(reason)

    def note_error(self, detail: str | None) -> None:
        self.events += 1
        if detail is not None:
            self.error_detail = detail

    def note_unsupported(self) -> None:
        self.unsupported_shape = True

    def verdict(self, http_ok: bool, framing_ok: bool, read_error: str | None = None) -> str:
        """One terminal outcome: ok, http_error, provider_error, truncated, or protocol_error."""
        if self.error_detail is not None:
            return "provider_error"
        if not http_ok:
            return "http_error"
        if read_error is not None or not framing_ok:
            return "truncated"
        if self.done or self.finish_reason is not None:
            return "ok"
        if self.events == 0 and self.malformed > 0:
            return "protocol_error"
        return "truncated"



class JsonlWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()

    async def emit(self, row: dict[str, Any]) -> None:
        async with self.lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
                stream.flush()


class ChunkDecoder:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.remaining: int | None = None
        self.done = False

    def feed(self, data: bytes) -> bytes:
        self.buffer.extend(data)
        decoded = bytearray()
        while not self.done:
            if self.remaining is None:
                separator = self.buffer.find(b"\r\n")
                if separator < 0:
                    break
                size_line = bytes(self.buffer[:separator])
                del self.buffer[: separator + 2]
                try:
                    self.remaining = int(size_line.split(b";", 1)[0].strip(), 16)
                except ValueError as exc:
                    raise ValueError("invalid chunk size") from exc
                if self.remaining == 0:
                    self.done = True
                    break
            if len(self.buffer) < self.remaining + 2:
                break
            decoded.extend(self.buffer[: self.remaining])
            del self.buffer[: self.remaining + 2]
            self.remaining = None
        return bytes(decoded)


class SseParser:
    def __init__(self, on_payload: Any) -> None:
        self.buffer = ""
        self.data: list[str] = []
        self.on_payload = on_payload

    def feed(self, data: bytes, now: float) -> None:
        self.buffer += data.decode("utf-8", "replace")
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._line(line.rstrip("\r"), now)

    def finish(self, now: float) -> None:
        if self.buffer:
            self._line(self.buffer.rstrip("\r"), now)
            self.buffer = ""
        self._flush(now)

    def _line(self, line: str, now: float) -> None:
        if line == "":
            self._flush(now)
        elif line.startswith("data:"):
            self.data.append(line[5:].lstrip())

    def _flush(self, now: float) -> None:
        if self.data:
            self.on_payload("\n".join(self.data), now)
            self.data.clear()
def join_upstream_path(base_url: str, request_path: str) -> str:
    from benching.benchmark.security import validate_endpoint

    try:
        validate_endpoint(base_url)
    except SystemExit as exc:
        raise ValueError(f"unsafe configured upstream: {exc.code or exc}") from None
    base = urlsplit(base_url.strip())
    path = request_path if request_path.startswith("/") else "/" + request_path
    return base.path.rstrip("/") + path


def configured_upstream(base_url: str) -> tuple[str, int]:
    from benching.benchmark.security import validate_endpoint

    try:
        validate_endpoint(base_url)
    except SystemExit as exc:
        raise ValueError(f"unsafe configured upstream: {exc.code or exc}") from None
    parsed = urlsplit(base_url.strip())
    # validate_endpoint guarantees https + hostname; port defaults to 443.
    assert parsed.hostname is not None
    return parsed.hostname, parsed.port or 443


class Proxy:
    def __init__(
        self,
        events: JsonlWriter,
        routes: dict[str, dict[str, str]],
        auth_token: str | None = None,
        connect_timeout: float = UPSTREAM_CONNECT_TIMEOUT,
        header_timeout: float = UPSTREAM_HEADER_TIMEOUT,
        read_timeout: float = UPSTREAM_READ_TIMEOUT,
        overall_timeout: float = UPSTREAM_OVERALL_TIMEOUT,
    ) -> None:
        self.events = events
        self.routes = routes
        # Run-scoped authentication secret. None disables authentication and
        # exists only for unit tests of unrelated behavior; production runs
        # launched by benching.benchmark.runner always configure a per-run token.
        # Compared with hmac.compare_digest; never logged or echoed.
        self.auth_token = auth_token
        self.connect_timeout = connect_timeout
        self.header_timeout = header_timeout
        self.read_timeout = read_timeout
        self.overall_timeout = overall_timeout
        self.inflight: dict[str, int] = defaultdict(int)
        self.lock = asyncio.Lock()

    def _check_auth(self, headers: dict[str, str]) -> bool:
        if self.auth_token is None:
            return True
        presented = headers.get(PROXY_AUTH_HEADER, "")
        return bool(presented) and hmac.compare_digest(presented, self.auth_token)

    async def _emit_timeout(self, state: dict[str, Any], start: float, error_type: str, message: str) -> None:
        """Emit one terminal row for an upstream deadline without secrets."""
        state["completion_status"] = "timeout"
        state["provider_failure"] = True
        state["error_type"] = error_type
        state["error_message"] = redact(message)
        state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
        state["completed_at_utc"] = utc()
        await self.events.emit(state)

    def _classify_eof(
        self,
        state: dict[str, Any],
        start: float,
        tracker: StreamTracker,
        http_ok: bool,
        framing_ok: bool,
        read_error: str | None,
    ) -> None:
        """Apply the tracker's terminal verdict to one forwarded request.

        Exactly one outcome: success requires a supported terminal marker
        ([DONE], finish/stop reason, or parsed non-SSE content) with no
        provider error. EOF, resets, and framing gaps classify as
        truncated/protocol_error, never success. Partial captured output
        is retained for diagnostics; success rates key off ``success``.
        """
        verdict = tracker.verdict(http_ok, framing_ok, read_error)
        state["completion_status"] = verdict
        state["success"] = verdict == "ok"
        state["provider_failure"] = verdict in ("http_error", "provider_error", "truncated", "protocol_error")
        state["stream_completed"] = verdict == "ok"
        if verdict == "truncated":
            if read_error is not None:
                state["error_type"] = read_error
                state["error_message"] = redact(f"provider connection reset: {read_error}")
            else:
                state["error_type"] = "truncated_stream"
                state["error_message"] = redact("stream ended without a terminal marker")
        elif verdict == "protocol_error":
            state["error_type"] = "protocol_error"
            state["error_message"] = redact(
                f"stream had {tracker.malformed} malformed events and no terminal marker"
            )
        elif verdict == "provider_error":
            state["error_type"] = "provider_error"
            state["error_message"] = tracker.error_detail or "provider error"
        state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
        state["completed_at_utc"] = utc()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        started_mono = time.monotonic()
        started_at = utc()
        request_id = uuid.uuid4().hex
        state: dict[str, Any] = {
            "schema_version": 1,
            "event_type": "inference",
            "request_id": request_id,
            "started_at_utc": started_at,
            "provider": None,
            "provider_plan": None,
            "provider_plan_tier": "unknown",
            "run_id": None,
            "task_id": None,
            "trial_id": None,
            "agent_invocation_id": None,
            "model": None,
            "provider_request_id": None,
            "routing": {"backend": None, "region": None},
            "timing": {
                "response_headers_ms": None,
                "first_stream_byte_ms": None,
                "first_content_output_ms": None,
                "last_content_output_ms": None,
                "stream_completed_ms": None,
            },
            "tokens": {
                "input_provider": None,
                "output_provider": None,
                "total_provider": None,
                "cache_read": None,
                "cache_write": None,
            },
            "usage_source": "unavailable",
            "finish_reason": None,
            "http_status": None,
            "success": False,
            "stream_completed": False,
            "completion_status": None,
            "downstream_cancelled": False,
            "provider_failure": False,
            "error_type": None,
            "error_message": None,
            "request_body": None,
            "response_body": None,
            "response_headers": {},
            "output_text": "",
            "output_text_truncated": False,
            "output_unsupported": False,
        }
        provider = "unknown"
        try:
            try:
                request_line = await reader.readline()
                if not request_line:
                    return
                if len(request_line) > MAX_REQUEST_LINE:
                    raise _DownstreamError("request line too large")
                try:
                    method, path, version = request_line.decode("latin1").strip().split(" ", 2)
                except ValueError:
                    raise _DownstreamError("malformed request line") from None
                headers: dict[str, str] = {}
                header_bytes = 0
                while True:
                    line = await reader.readline()
                    header_bytes += len(line)
                    if header_bytes > MAX_HEADERS:
                        raise _DownstreamError("headers too large")
                    if line in (b"\r\n", b"\n", b""):
                        break
                    try:
                        key, value = line.decode("latin1").split(":", 1)
                    except ValueError:
                        raise _DownstreamError("malformed header") from None
                    headers[key.lower()] = value.strip()
            except _DownstreamError:
                raise
            except Exception as exc:
                raise _DownstreamError("malformed request") from exc
            normalized_path = "/" + path.lstrip("/").split("?", 1)[0]
            if normalized_path == HEALTH_PATH:
                # Authenticated readiness probe: proves this listener is this
                # run's proxy child. Never forwarded, never logged as telemetry.
                try:
                    presented = headers.pop(PROXY_AUTH_HEADER, "")
                    if self.auth_token is not None and presented and hmac.compare_digest(presented, self.auth_token):
                        await send_response(writer, 200, "OK", b'{"ok":true}')
                    else:
                        await send_response(writer, 403, "Forbidden", _error_body("forbidden"))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                return
            if not self._check_auth(headers):
                # Unauthenticated: rejected before trusting headers,
                # creating telemetry, or forwarding upstream.
                try:
                    await send_response(writer, 403, "Forbidden", _error_body("forbidden"))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                return
            provider = headers.pop("x-benchmark-provider", "")
            if not provider:
                provider = path.lstrip("/").split("/", 1)[0]
            route = self.routes.get(provider)
            if route is None:
                raise ValueError(f"unknown benchmark provider: {provider}")
            state["provider"] = provider
            state["provider_plan"] = route.get("plan")
            state["provider_plan_tier"] = route.get("plan_tier", "unknown")
            state["run_id"] = headers.pop("x-benchmark-run-id", None)
            state["task_id"] = headers.pop("x-benchmark-task", None)
            state["trial_id"] = headers.pop("x-benchmark-trial", None)
            state["agent_invocation_id"] = headers.pop("x-benchmark-agent-invocation-id", None)
            for key in BENCHMARK_HEADERS:
                headers.pop(key, None)
            path = "/" + path.lstrip("/")
            prefix = "/" + provider
            if path == prefix:
                path = "/"
            elif path.startswith(prefix + "/"):
                path = path[len(prefix):]
            path = "/" + path.lstrip("/")
            if not path.startswith("/"):
                path = "/" + path
            upstream = route["upstream"]
            host, port = configured_upstream(upstream)
            target_path = join_upstream_path(upstream, path)
            state["request_path"] = path
            state["target_path"] = target_path
            try:
                content_length = int(headers.get("content-length", "0"))
            except (TypeError, ValueError):
                raise _DownstreamError("invalid content length") from None
            if content_length < 0 or content_length > MAX_BODY:
                raise _DownstreamError("request body too large")
            try:
                body = await reader.readexactly(content_length) if content_length else b""
            except asyncio.IncompleteReadError as exc:
                raise _DownstreamError("incomplete request body") from exc
            # C10: parsing state starts initialized; malformed downstream
            # bodies are 400-class client errors, never provider failures.
            request_json: Any = None
            try:
                request_json = json.loads(body) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise _DownstreamError("malformed request body") from exc
            if isinstance(request_json, dict):
                state["model"] = request_json.get("model")
                state["request_body"] = redact_json(request_json)
            if isinstance(request_json, dict) and route.get("reasoning") == "disabled":
                request_json["reasoning"] = {"enabled": False}
                body = json.dumps(request_json, separators=(",", ":")).encode("utf-8")
                headers["content-length"] = str(len(body))
            async with self.lock:
                state["active_requests_at_start"] = self.inflight[provider]
                self.inflight[provider] += 1
            try:
                await self.forward(host, port, method, target_path, version, headers, body, writer, state, started_mono)
            finally:
                async with self.lock:
                    self.inflight[provider] -= 1
        except _DownstreamError:
            # Malformed client request: 400-class response, no provider
            # request, no provider_failure telemetry row.
            try:
                await send_response(writer, 400, "Bad Request", _error_body("bad request"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        except Exception as exc:
            state["completion_status"] = "error"
            state["provider_failure"] = True
            state["error_type"] = type(exc).__name__
            state["error_message"] = redact(str(exc))
            state["completed_at_utc"] = utc()
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - started_mono) * 1000, 3)
            await self.events.emit(state)
            try:
                await send_response(writer, 502, "Bad Gateway", _error_body("proxy failure"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def _overall_expired(self, start: float) -> bool:
        return (time.monotonic() - start) > self.overall_timeout

    async def forward(self, host: str, port: int, method: str, path: str, version: str, headers: dict[str, str], body: bytes, client: asyncio.StreamWriter, state: dict[str, Any], start: float) -> None:
        try:
            upstream_reader, upstream = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=True, server_hostname=host),
                self.connect_timeout,
            )
        except TimeoutError:
            await self._emit_timeout(state, start, "upstream_connect_timeout", "upstream connection timed out")
            try:
                await send_response(client, 502, "Bad Gateway", _error_body("proxy failure"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        except (OSError, ValueError) as exc:
            raise ConnectionError(f"upstream connection failed: {type(exc).__name__}") from exc
        try:
            forwarded_response_head = False
            headers = dict(headers)
            headers["host"] = host
            headers["connection"] = "close"
            headers.pop("proxy-connection", None)
            wire_request = f"{method} {path} {version}\r\n".encode("latin1")
            wire_request += b"".join(f"{key}: {value}\r\n".encode("latin1") for key, value in headers.items())
            wire_request += b"\r\n" + body
            upstream.write(wire_request)
            await upstream.drain()
            try:
                status_line = await asyncio.wait_for(upstream_reader.readline(), self.header_timeout)
            except TimeoutError as exc:
                raise _UpstreamTimeout("header") from exc
            except (ConnectionResetError, ConnectionError) as exc:
                raise _NoUpstreamResponse(type(exc).__name__) from exc
            if not status_line:
                raise _NoUpstreamResponse(None)
            try:
                client.write(status_line)
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                raise _DownstreamGone() from exc
            try:
                state["http_status"] = int(status_line.split()[1])
            except (IndexError, ValueError) as exc:
                raise ValueError("invalid upstream status") from exc
            response_headers: dict[str, str] = {}
            read_error: str | None = None
            framing_ok = True
            raw_total = 0
            while True:
                if self._overall_expired(start):
                    raise _UpstreamTimeout("overall")
                try:
                    line = await asyncio.wait_for(upstream_reader.readline(), self.header_timeout)
                except TimeoutError as exc:
                    raise _UpstreamTimeout("header") from exc
                except (ConnectionResetError, ConnectionError) as exc:
                    # Read-side failure: the provider went away mid-headers.
                    read_error = type(exc).__name__
                    break
                try:
                    await safe_write(client, line)
                except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                    raise _DownstreamGone() from exc
                if line in (b"\r\n", b"\n", b""):
                    break
                if b":" in line:
                    key, value = line.decode("latin1").split(":", 1)
                    response_headers[key.lower()] = value.strip()
            state["response_headers"] = redact_json(response_headers)
            state["timing"]["response_headers_ms"] = round((time.monotonic() - start) * 1000, 3)
            state["provider_request_id"] = response_headers.get("x-request-id") or response_headers.get("request-id")
            state["routing"] = {
                "backend": response_headers.get("x-backend") or response_headers.get("x-upstream") or response_headers.get("x-provider-backend"),
                "region": response_headers.get("x-region") or response_headers.get("x-provider-region"),
            }
            try:
                await client.drain()
            except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                raise _DownstreamGone() from exc
            forwarded_response_head = True
            chunked = "chunked" in response_headers.get("transfer-encoding", "").lower()
            encoding = response_headers.get("content-encoding", "").lower()
            decoder = ChunkDecoder() if chunked else None
            decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS) if "gzip" in encoding else None
            content_type = response_headers.get("content-type", "").lower()
            is_sse = "text/event-stream" in content_type
            response_buffer = bytearray()
            output_parts: list[str] = []
            captured = 0
            first_stream = False
            first_content = False
            last_content: float | None = None

            def capture_output(value: str) -> None:
                nonlocal captured
                if not value:
                    return
                if captured >= MAX_CAPTURE:
                    state["output_text_truncated"] = True
                    return
                remaining = MAX_CAPTURE - captured
                piece = value[:remaining]
                output_parts.append(piece)
                captured += len(piece.encode("utf-8"))
                if len(piece) != len(value):
                    state["output_text_truncated"] = True

            tracker = StreamTracker()

            def process_payload(payload: str, now: float) -> None:
                nonlocal first_content, last_content
                if payload.strip() == "[DONE]":
                    tracker.note_done()
                    return
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    tracker.note_malformed()
                    return
                if not isinstance(event, dict):
                    tracker.note_malformed()
                    return
                tracker.note_payload()
                detail = provider_error_detail(event)
                if detail is not None:
                    tracker.note_error(detail)
                update_usage(state, event.get("usage"))
                update_usage(state, event.get("metrics"))
                message = event.get("message")
                if isinstance(message, dict):
                    update_usage(state, message.get("usage"))
                choices = event.get("choices")
                if isinstance(choices, list):
                    for choice in choices:
                        if isinstance(choice, dict) and choice.get("finish_reason") is not None:
                            state["finish_reason"] = choice["finish_reason"]
                            tracker.note_finish(choice["finish_reason"])
                delta = event.get("delta")
                if isinstance(delta, dict) and delta.get("stop_reason") is not None:
                    state["finish_reason"] = delta["stop_reason"]
                    tracker.note_finish(delta["stop_reason"])
                for key in ("finish_reason", "stop_reason"):
                    value = event.get(key)
                    if value is not None:
                        state["finish_reason"] = value
                        tracker.note_finish(value)
                parts, supported = extract_deltas(event)
                if not supported:
                    tracker.note_unsupported()
                for value in parts:
                    capture_output(value)
                    if not first_content:
                        first_content = True
                        state["timing"]["first_content_output_ms"] = round((now - start) * 1000, 3)
                    last_content = now

            sse = SseParser(process_payload)
            # Readline-based iteration matches StreamReader.__aiter__ chunk
            # semantics; each wait is bounded so a stalled upstream cannot
            # hang the proxied request indefinitely. Read-side transport
            # failures are provider-side (read_error); downstream write
            # failures raise _DownstreamGone and never blame the provider.
            while True:
                if self._overall_expired(start):
                    raise _UpstreamTimeout("overall")
                try:
                    chunk = await asyncio.wait_for(upstream_reader.readline(), self.read_timeout)
                except TimeoutError as exc:
                    raise _UpstreamTimeout("read") from exc
                except (ConnectionResetError, ConnectionError) as exc:
                    read_error = type(exc).__name__
                    break
                if not chunk:
                    break
                now = time.monotonic()
                if not first_stream:
                    first_stream = True
                    state["timing"]["first_stream_byte_ms"] = round((now - start) * 1000, 3)
                try:
                    await safe_write(client, chunk)
                except (BrokenPipeError, ConnectionResetError, OSError) as exc:
                    raise _DownstreamGone() from exc
                raw_total += len(chunk)
                try:
                    decoded = decoder.feed(chunk) if decoder else chunk
                    if decompressor:
                        decoded = decompressor.decompress(decoded)
                except Exception:
                    framing_ok = False
                    break
                if not is_sse and len(response_buffer) < MAX_CAPTURE:
                    response_buffer.extend(decoded[: MAX_CAPTURE - len(response_buffer)])
                if is_sse:
                    sse.feed(decoded, now)
                else:
                    sse.feed(decoded, now)
            if decompressor:
                tail = decompressor.flush()
                if tail:
                    sse.feed(tail, time.monotonic())
                    if not is_sse:
                        response_buffer.extend(tail[: MAX_CAPTURE - len(response_buffer)])
            sse.finish(time.monotonic())
            completed = time.monotonic()
            if not is_sse and response_buffer:
                state["response_body"] = redact(response_buffer.decode("utf-8", "replace"))
                if not state["output_text"]:
                    try:
                        process_payload(response_buffer.decode("utf-8", "replace"), completed)
                    except Exception:
                        pass
            state["output_text"] = "".join(output_parts)
            state["output_unsupported"] = tracker.unsupported_shape
            http_status = state["http_status"]
            http_ok = isinstance(http_status, int) and 200 <= http_status < 300
            if chunked:
                framing_ok = framing_ok and decoder.done
            else:
                try:
                    declared = response_headers.get("content-length")
                    declared_length = int(str(declared).strip()) if declared is not None else None
                except (TypeError, ValueError):
                    declared_length = None
                if declared_length is not None:
                    framing_ok = framing_ok and raw_total >= declared_length
            self._classify_eof(state, start, tracker, http_ok, framing_ok, read_error)
            if last_content is not None:
                state["timing"]["last_content_output_ms"] = round((last_content - start) * 1000, 3)
            await self.events.emit(state)
        except _UpstreamTimeout as exc:
            # Bounded deadline exceeded: provider-side transport failure,
            # distinguishable from cancellation, malformed input, and HTTP
            # errors via error_type. A 502 goes downstream only when no
            # upstream bytes were forwarded yet.
            await self._emit_timeout(state, start, f"upstream_{exc.stage}_timeout", f"upstream {exc.stage} timed out")
            if not forwarded_response_head:
                try:
                    await send_response(client, 502, "Bad Gateway", _error_body("proxy failure"))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
        except _NoUpstreamResponse as exc:
            state["completion_status"] = "truncated"
            state["success"] = False
            state["stream_completed"] = False
            state["provider_failure"] = True
            if exc.read_error is not None:
                state["error_type"] = exc.read_error
                state["error_message"] = redact(f"provider connection reset: {exc.read_error}")
            else:
                state["error_type"] = "truncated_stream"
                state["error_message"] = redact("upstream closed without a response")
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
            state["completed_at_utc"] = utc()
            await self.events.emit(state)
            try:
                await send_response(client, 502, "Bad Gateway", _error_body("proxy failure"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        except _DownstreamGone:
            state["completion_status"] = "cancelled"
            state["downstream_cancelled"] = True
            state["provider_failure"] = False
            state["error_type"] = "downstream_disconnect"
            state["error_message"] = "client disconnected during upstream stream"
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
            state["completed_at_utc"] = utc()
            await self.events.emit(state)
        except asyncio.CancelledError:
            state["completion_status"] = "cancelled"
            state["downstream_cancelled"] = True
            state["provider_failure"] = False
            state["error_type"] = "downstream_disconnect"
            state["error_message"] = "client disconnected during upstream stream"
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
            state["completed_at_utc"] = utc()
            await self.events.emit(state)
            raise
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            # Read-side or otherwise unclassified transport failure that
            # escaped inner handling: provider-side, fail closed with one
            # terminal row. Downstream write failures are converted to
            # _DownstreamGone at their write sites and never reach here.
            state["completion_status"] = "error"
            state["provider_failure"] = True
            state["error_type"] = type(exc).__name__
            state["error_message"] = redact(str(exc))
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
            state["completed_at_utc"] = utc()
            await self.events.emit(state)
            try:
                await send_response(client, 502, "Bad Gateway", _error_body("proxy failure"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        finally:
            upstream.close()
            try:
                await upstream.wait_closed()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass


def redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if key.lower() in {"authorization", "api_key", "apikey", "x-api-key"} else redact_json(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value


def update_usage(state: dict[str, Any], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    details = usage.get("prompt_tokens_details") or {}
    values = {
        "input_provider": usage.get("input_tokens", usage.get("prompt_tokens", usage.get("input"))),
        "output_provider": usage.get("output_tokens", usage.get("completion_tokens", usage.get("output"))),
        "total_provider": usage.get("total_tokens", usage.get("total")),
        "cache_read": usage.get("cache_read_input_tokens", usage.get("cacheRead")),
        "cache_write": usage.get("cache_creation_input_tokens", usage.get("cacheWrite")),
    }
    if values["cache_read"] is None and isinstance(details, dict):
        values["cache_read"] = details.get("cached_tokens") or details.get("cache_read_input_tokens")
    if values["cache_write"] is None and isinstance(details, dict):
        values["cache_write"] = details.get("cache_creation_tokens") or details.get("cache_write_input_tokens")
    for key, value in values.items():
        if value is not None:
            try:
                state["tokens"][key] = int(value)
                state["usage_source"] = "reported"
            except (TypeError, ValueError):
                pass


async def safe_write(writer: asyncio.StreamWriter, data: bytes) -> None:
    if not data:
        return
    try:
        writer.write(data)
        await asyncio.wait_for(writer.drain(), DOWNSTREAM_WRITE_TIMEOUT)
    except (BrokenPipeError, ConnectionResetError, OSError):
        raise
    except TimeoutError as exc:
        raise BrokenPipeError("downstream write timed out") from exc


async def send_response(writer: asyncio.StreamWriter, status: int, reason: str, body: bytes, content_type: str = "application/json") -> None:
    """Send one complete HTTP response with a computed Content-Length.

    The body bytes are built first and ``len(body)`` is declared, so
    hardcoded framing mismatches (C11) cannot recur.
    """
    head = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin1")
    await safe_write(writer, head + body)


def _error_body(message: str) -> bytes:
    return json.dumps({"error": message}, separators=(",", ":")).encode("utf-8")


def load_routes(path: Path) -> dict[str, dict[str, str]]:
    from benching.benchmark.security import validate_endpoint

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("routes file must contain an object")
    routes: dict[str, dict[str, str]] = {}
    for provider, route in value.items():
        if not isinstance(provider, str) or not isinstance(route, dict):
            raise ValueError("invalid provider route")
        upstream = route.get("upstream")
        if not isinstance(upstream, str):
            raise ValueError(f"invalid upstream for {provider}")
        try:
            validate_endpoint(upstream)
        except SystemExit as exc:
            raise ValueError(f"invalid upstream for {provider}: {exc.code or exc}") from None
        routes[provider] = {
            "upstream": upstream,
            "plan": str(route.get("plan", "")),
            "plan_tier": str(route.get("plan_tier") or "unknown"),
            "reasoning": str(route.get("reasoning", "default")),
        }
    return routes


def load_auth_token(path: Path) -> str:
    """Load the per-run proxy auth token from its private file.

    Fails closed: a missing or malformed file refuses to start rather
    than serving an unauthenticated proxy.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable proxy auth file: {path}") from exc
    token = value.get("auth_token") if isinstance(value, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError(f"unreadable proxy auth file: {path}")
    return token


async def serve(events: Path, routes_path: Path, port: int, auth_token_file: Path) -> None:
    proxy = Proxy(JsonlWriter(events), load_routes(routes_path), auth_token=load_auth_token(auth_token_file))
    server = await asyncio.start_server(proxy.handle, "0.0.0.0", port)
    print(f"telemetry proxy listening on {port}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
    except (NotImplementedError, RuntimeError, OSError):
        # Native Windows cannot install asyncio signal handlers; fall back
        # to synchronous handlers. Execution itself remains Linux/WSL-only.
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, lambda *_args: loop.call_soon_threadsafe(stop.set))
            except (OSError, RuntimeError, ValueError):
                pass
    await stop.wait()
    server.close()
    try:
        await asyncio.wait_for(server.wait_closed(), SERVER_SHUTDOWN_TIMEOUT)
    except TimeoutError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--routes", required=True, type=Path)
    parser.add_argument("--auth-token-file", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(serve(args.events, args.routes, args.port, args.auth_token_file))


if __name__ == "__main__":
    main()

