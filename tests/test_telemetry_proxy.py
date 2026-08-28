from __future__ import annotations

import asyncio
import json
from pathlib import Path

from proxy.telemetry_proxy import ChunkDecoder, JsonlWriter, Proxy, SseParser, join_upstream_path, load_routes, redact, update_usage


class _FakeWriter:
    def write(self, data: bytes) -> None: ...
    async def drain(self) -> None: ...
    def close(self) -> None: ...
    async def wait_closed(self) -> None: ...


async def _fake_reader(request: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(request)
    reader.feed_eof()
    return reader


def test_redaction_removes_common_credentials() -> None:
    value = redact("Authorization: Bearer secret api_key=other API key: fifth x-api-key: third token=fourth")
    assert value is not None
    assert all(secret not in value for secret in ("secret", "other", "fifth", "third", "fourth"))


def test_jsonl_is_parseable(tmp_path: Path) -> None:
    async def emit() -> None:
        await JsonlWriter(tmp_path / "events.jsonl").emit({"schema_version": 1, "event_type": "inference"})
    asyncio.run(emit())
    assert json.loads((tmp_path / "events.jsonl").read_text()) == {"schema_version": 1, "event_type": "inference"}


def test_chunk_decoder_handles_split_chunks() -> None:
    decoder = ChunkDecoder()
    assert decoder.feed(b"4\r\nte") == b""
    assert decoder.feed(b"st\r\n3\r\nabc\r\n0\r\n\r\n") == b"testabc"
    assert decoder.done


def test_sse_parser_joins_data_lines() -> None:
    payloads: list[str] = []
    parser = SseParser(lambda payload, _now: payloads.append(payload))
    parser.feed(b"event: message\ndata: {\"a\":\ndata: 1}\n\n", 1.0)
    parser.finish(2.0)
    assert payloads == ['{"a":\n1}']


def test_usage_preserves_provider_values() -> None:
    state = {"tokens": {"input_provider": None, "output_provider": None, "total_provider": None, "cache_read": None, "cache_write": None}, "usage_source": "unavailable"}
    update_usage(state, {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14, "prompt_tokens_details": {"cached_tokens": 3}})
    assert state["tokens"]["input_provider"] == 10
    assert state["tokens"]["output_provider"] == 4
    assert state["tokens"]["cache_read"] == 3
    assert state["usage_source"] == "reported"


def test_reasoning_disabled_injected_into_forwarded_body(tmp_path: Path) -> None:
    # The proxy must add reasoning.enabled=false to the JSON body so providers
    # defaulting to reasoning-on (ElectronHub) match Kourier's behavior.
    import proxy.telemetry_proxy as mod

    captured: dict = {}

    async def fake_forward(self, host, port, method, path, version, headers, body, client, state, start):
        captured["body"] = json.loads(body)
        captured["content_length"] = headers.get("content-length")

    original = mod.Proxy.forward
    mod.Proxy.forward = fake_forward
    try:
        proxy = mod.Proxy(mod.JsonlWriter(Path("/tmp/unused-events.jsonl")), {"electronhub": {"upstream": "https://example.test/v1", "plan": "dev_coding", "plan_tier": "unknown"}})
        body = b'{"model":"deepseek-v4-flash-0731:dev","messages":[]}'
        request = b"POST /electronhub/chat/completions HTTP/1.1\r\nX-Benchmark-Provider: electronhub\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        async def run() -> None:
            await proxy.handle(await _fake_reader(request), _FakeWriter())
        asyncio.run(run())
    finally:
        mod.Proxy.forward = original
    assert captured["body"]["reasoning"] == {"enabled": False}
    assert captured["content_length"] == str(len(json.dumps(captured["body"], separators=(",", ":")).encode()))
    proxy = Proxy(JsonlWriter(tmp_path / "events.jsonl"), {"kourier": {"upstream": "https://example.test/v1", "plan": "standard"}})
    assert not hasattr(proxy, "semaphores")


def test_provider_url_joining_never_duplicates_v1() -> None:
    assert join_upstream_path("https://api.kourier.sh/v1", "/chat/completions") == "/v1/chat/completions"
    assert join_upstream_path("https://api.electronhub.ai/v1/", "chat/completions") == "/v1/chat/completions"


def test_routes_reject_non_https(tmp_path: Path) -> None:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps({"bad": {"upstream": "http://example.test/v1"}}))
    try:
        load_routes(path)
    except ValueError as exc:
        assert "invalid upstream" in str(exc)
    else:
        raise AssertionError("insecure route accepted")
