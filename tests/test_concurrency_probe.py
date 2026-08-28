from __future__ import annotations

import json

import benchmark.concurrency_probe as probe


def test_parse_stream_detects_content_and_finish() -> None:
    body = b'data: {"choices":[{"delta":{"content":"one"},"finish_reason":null}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    first, finish, usage = probe.parse_stream(body)
    assert first is True
    assert finish == "stop"
    assert usage is None


def test_staged_probe_stops_after_first_rejected_stage(tmp_path, monkeypatch) -> None:
    calls: list[int] = []

    def fake_stage(provider, plan, tier, endpoint, api_model, key, requested):
        calls.append(requested)
        return {
            "requested_concurrency": requested,
            "successful_simultaneous_streams": requested if requested < 3 else 2,
            "rejected_simultaneous_streams": 0 if requested < 3 else 1,
            "maximum_simultaneous_requests_observed": min(requested, 2),
            "all_streams_successful": requested < 3,
            "requests": [{"http_status": 200 if requested < 3 else 429, "stream_success": requested < 3}],
        }

    monkeypatch.setattr(probe, "simultaneous", fake_stage)
    summary_path, jsonl_path = probe.run_probe("electronhub", {"plan": "dev_coding", "plan_tier": "unknown"}, "https://example.test/v1", "deepseek-v4-flash-0731:dev", "secret", tmp_path)
    summary = json.loads(summary_path.read_text())
    assert calls == [2, 3]
    assert summary["highest_verified_concurrency"] == 2
    assert summary["first_rejected_concurrency"] == 3
    assert summary["rejection_status"] == 429
    assert summary["limit_verified"] is True
    assert len(jsonl_path.read_text().splitlines()) == 2
