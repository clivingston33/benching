#!/usr/bin/env python3
"""Transparent OpenAI-compatible streaming proxy with per-run JSONL telemetry."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time
import uuid
import zlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
}


def utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    import re

    patterns = (
        (r"(?i)(authorization\s*:\s*(?:bearer\s+)?)[^\s,;\"]+", r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;\"]+", r"\1[REDACTED]"),
        (r"(?i)(x-api-key\s*[:=]\s*)[^\s,;\"]+", r"\1[REDACTED]"),
        (r"(?i)(token\s*[:=]\s*)[^\s,;\"]+", r"\1[REDACTED]"),
    )
    for pattern, replacement in patterns:
        value = re.sub(pattern, replacement, value)
    return value


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
    base = urlsplit(base_url)
    if base.scheme != "https" or not base.hostname:
        raise ValueError("unsafe configured upstream")
    path = request_path if request_path.startswith("/") else "/" + request_path
    return base.path.rstrip("/") + path


def configured_upstream(base_url: str) -> tuple[str, int]:
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("unsafe configured upstream")
    return parsed.hostname, parsed.port or 443


class Proxy:
    def __init__(self, events: JsonlWriter, routes: dict[str, dict[str, str]]) -> None:
        self.events = events
        self.routes = routes
        self.inflight: dict[str, int] = defaultdict(int)
        self.lock = asyncio.Lock()

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
            "downstream_cancelled": False,
            "provider_failure": False,
            "error_type": None,
            "error_message": None,
            "request_body": None,
            "response_body": None,
            "response_headers": {},
            "output_text": "",
            "output_text_truncated": False,
        }
        provider = "unknown"
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            if len(request_line) > MAX_REQUEST_LINE:
                raise ValueError("request line too large")
            method, path, version = request_line.decode("latin1").strip().split(" ", 2)
            headers: dict[str, str] = {}
            header_bytes = 0
            while True:
                line = await reader.readline()
                header_bytes += len(line)
                if header_bytes > MAX_HEADERS:
                    raise ValueError("headers too large")
                if line in (b"\r\n", b"\n", b""):
                    break
                key, value = line.decode("latin1").split(":", 1)
                headers[key.lower()] = value.strip()
            content_length = int(headers.get("content-length", "0"))
            if content_length < 0 or content_length > MAX_BODY:
                raise ValueError("request body too large")
            body = await reader.readexactly(content_length) if content_length else b""
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
                request_json = json.loads(body) if body else {}
                if isinstance(request_json, dict):
                    state["model"] = request_json.get("model")
                    state["request_body"] = redact_json(request_json)
            except (json.JSONDecodeError, UnicodeDecodeError):
                state["request_body"] = "<non-json>"
            async with self.lock:
                state["active_requests_at_start"] = self.inflight[provider]
                self.inflight[provider] += 1
            try:
                await self.forward(host, port, method, target_path, version, headers, body, writer, state, started_mono)
            finally:
                async with self.lock:
                    self.inflight[provider] -= 1
        except Exception as exc:
            state["provider_failure"] = True
            state["error_type"] = type(exc).__name__
            state["error_message"] = redact(str(exc))
            state["completed_at_utc"] = utc()
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - started_mono) * 1000, 3)
            await self.events.emit(state)
            await safe_write(writer, b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: application/json\r\nContent-Length: 31\r\nConnection: close\r\n\r\n{\"error\":\"proxy failure\"}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    async def forward(self, host: str, port: int, method: str, path: str, version: str, headers: dict[str, str], body: bytes, client: asyncio.StreamWriter, state: dict[str, Any], start: float) -> None:
        upstream_reader, upstream = await asyncio.open_connection(host, port, ssl=True, server_hostname=host)
        try:
            headers = dict(headers)
            headers["host"] = host
            headers["connection"] = "close"
            headers.pop("proxy-connection", None)
            wire_request = f"{method} {path} {version}\r\n".encode("latin1")
            wire_request += b"".join(f"{key}: {value}\r\n".encode("latin1") for key, value in headers.items())
            wire_request += b"\r\n" + body
            upstream.write(wire_request)
            await upstream.drain()
            status_line = await upstream_reader.readline()
            if not status_line:
                raise ConnectionError("upstream returned no status")
            client.write(status_line)
            try:
                state["http_status"] = int(status_line.split()[1])
            except (IndexError, ValueError) as exc:
                raise ValueError("invalid upstream status") from exc
            response_headers: dict[str, str] = {}
            while True:
                line = await upstream_reader.readline()
                await safe_write(client, line)
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
            await client.drain()
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

            def process_payload(payload: str, now: float) -> None:
                nonlocal first_content, last_content
                if payload == "[DONE]":
                    return
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    return
                if not isinstance(event, dict):
                    return
                update_usage(state, event.get("usage"))
                update_usage(state, event.get("metrics"))
                message = event.get("message")
                if isinstance(message, dict):
                    update_usage(state, message.get("usage"))
                content_values: list[Any] = []
                choices = event.get("choices") or []
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta") or {}
                    message = choice.get("message") or {}
                    for value in (delta.get("content"), delta.get("text"), delta.get("reasoning_content"), delta.get("reasoning"), message.get("content")):
                        content_values.append(value)
                    for value in (delta.get("tool_calls"), message.get("tool_calls")):
                        if value not in (None, "", [], {}):
                            content_values.append(value)
                    if choice.get("finish_reason") is not None:
                        state["finish_reason"] = choice["finish_reason"]
                delta = event.get("delta") or {}
                if isinstance(delta, dict):
                    content_values.extend((delta.get("text"), delta.get("thinking"), delta.get("partial_json")))
                    if delta.get("stop_reason") is not None:
                        state["finish_reason"] = delta["stop_reason"]
                if event.get("type") in {"content_block_delta", "content_block_start"}:
                    block = event.get("content_block") or {}
                    if isinstance(block, dict):
                        content_values.append(block.get("text"))
                for value in content_values:
                    if value in (None, "", [], {}):
                        continue
                    if isinstance(value, str):
                        capture_output(value)
                    if not first_content:
                        first_content = True
                        state["timing"]["first_content_output_ms"] = round((now - start) * 1000, 3)
                    last_content = now

            sse = SseParser(process_payload)
            async for chunk in upstream_reader:
                now = time.monotonic()
                if not first_stream:
                    first_stream = True
                    state["timing"]["first_stream_byte_ms"] = round((now - start) * 1000, 3)
                await safe_write(client, chunk)
                decoded = decoder.feed(chunk) if decoder else chunk
                if decompressor:
                    decoded = decompressor.decompress(decoded)
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
            state["stream_completed"] = True
            state["success"] = isinstance(state["http_status"], int) and state["http_status"] < 400
            state["provider_failure"] = not state["success"]
            if last_content is not None:
                state["timing"]["last_content_output_ms"] = round((last_content - start) * 1000, 3)
            state["timing"]["stream_completed_ms"] = round((completed - start) * 1000, 3)
            state["completed_at_utc"] = utc()
            await self.events.emit(state)
        except (BrokenPipeError, ConnectionResetError, asyncio.CancelledError):
            state["downstream_cancelled"] = True
            state["provider_failure"] = False
            state["error_type"] = "downstream_disconnect"
            state["error_message"] = "client disconnected during upstream stream"
            state["timing"]["stream_completed_ms"] = round((time.monotonic() - start) * 1000, 3)
            state["completed_at_utc"] = utc()
            await self.events.emit(state)
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
        await writer.drain()
    except (BrokenPipeError, ConnectionResetError, OSError):
        raise


def load_routes(path: Path) -> dict[str, dict[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("routes file must contain an object")
    routes: dict[str, dict[str, str]] = {}
    for provider, route in value.items():
        if not isinstance(provider, str) or not isinstance(route, dict):
            raise ValueError("invalid provider route")
        upstream = route.get("upstream")
        if not isinstance(upstream, str) or not upstream.startswith("https://"):
            raise ValueError(f"invalid upstream for {provider}")
        routes[provider] = {"upstream": upstream, "plan": str(route.get("plan", ""))}
    return routes


async def serve(events: Path, routes_path: Path, port: int) -> None:
    proxy = Proxy(JsonlWriter(events), load_routes(routes_path))
    server = await asyncio.start_server(proxy.handle, "0.0.0.0", port)
    print(f"telemetry proxy listening on {port}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    server.close()
    await server.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--routes", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(serve(args.events, args.routes, args.port))


if __name__ == "__main__":
    main()
