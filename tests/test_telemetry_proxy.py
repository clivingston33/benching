from __future__ import annotations

import asyncio
import json
from pathlib import Path

from proxy.telemetry_proxy import ChunkDecoder, JsonlWriter, Proxy, SseParser, join_upstream_path, load_routes, redact, update_usage


def test_redaction_removes_common_credentials() -> None:
    value = redact("Authorization: Bearer secret api_key=other x-api-key: third token=fourth")
    assert value is not None
    assert "secret" not in value and "other" not in value and "third" not in value and "fourth" not in value


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


def test_proxy_has_no_provider_semaphores(tmp_path: Path) -> None:
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
