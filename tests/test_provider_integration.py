from __future__ import annotations

from benchmark.benchmarkctl import benchmark_settings, classify_validation, load_yaml, parse_stream_body, resolve


def test_provider_configs_have_distinct_api_models() -> None:
    config = load_yaml()
    assert benchmark_settings(config) == ("terminal-bench", "2.1", "deepseek-v4-flash-0731")
    kourier = config["providers"]["kourier"]
    electronhub = config["providers"]["electronhub"]
    assert kourier["api_model"] == "DSV4-Flash-0731"
    assert electronhub["api_model"] == "deepseek-v4-flash-0731:dev"
    assert kourier["api_model"] != electronhub["api_model"]

def test_plan_tiers_are_not_inferred() -> None:
    config = load_yaml()
    assert config["providers"]["kourier"]["plan_tier"] == "unknown"
    assert config["providers"]["electronhub"]["plan_tier"] == "unknown"


def test_resolve_uses_configured_api_model() -> None:
    config = load_yaml()
    endpoint, api_model = resolve("electronhub", config["providers"]["electronhub"])
    assert endpoint == "https://api.electronhub.ai/v1"
    assert api_model == "deepseek-v4-flash-0731:dev"


def test_stream_validation_detects_content_and_usage() -> None:
    body = b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: {"usage":{"prompt_tokens":2}}\n\ndata: [DONE]\n\n'
    first_content, usage = parse_stream_body(body)
    assert first_content is True
    assert usage == {"prompt_tokens": 2}

def test_validation_classifies_cloudflare_edge_denial() -> None:
    assert classify_validation({"status": 403, "server": "cloudflare", "cf_ray": "abc"}) == "edge_access_denied"


def test_stream_validation_detects_reasoning_or_text() -> None:
    body = b'data: {"choices":[{"delta":{"reasoning":"thinking"}}]}\n\ndata: [DONE]\n\n'
    assert parse_stream_body(body)[0] is True
