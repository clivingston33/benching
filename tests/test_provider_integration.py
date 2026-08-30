from __future__ import annotations

from benchmark.benchmarkctl import RunOptions, benchmark_settings, classify_validation, harbor_command, load_yaml, parse_stream_body, resolve


def test_provider_configs_have_distinct_api_models() -> None:
    config = load_yaml()
    assert benchmark_settings(config) == ("terminal-bench", "2.1", "deepseek-v4-flash-0731")
    kourier = config["providers"]["kourier"]
    electronhub = config["providers"]["electronhub"]
    assert kourier["api_model"] == "DSV4-Flash-0731"
    assert electronhub["api_model"] == "deepseek-v4-flash-0731:dev"
    assert kourier["api_model"] != electronhub["api_model"]


def test_harbor_command_preserves_agent_kwargs(tmp_path, monkeypatch) -> None:
    import benchmark.benchmarkctl as ctl

    monkeypatch.setattr(ctl, "executable", lambda name: name)
    command = harbor_command(
        RunOptions("kourier", "smoke"),
        {"auth_env": "KOURIER_API_KEY", "api": "openai-completions", "plan": None},
        "https://api.kourier.sh/v1",
        "DSV4-Flash-0731",
        "deepseek-v4-flash-0731",
        tmp_path,
        ["task-1"],
    )
    kwargs = [command[index + 1] for index, value in enumerate(command) if value == "--agent-kwarg"]
    assert kwargs == [
        "provider=kourier",
        "provider_plan=",
        "benchmark_model=deepseek-v4-flash-0731",
        "model=DSV4-Flash-0731",
        "upstream=https://api.kourier.sh/v1",
        "api_key_env=KOURIER_API_KEY",
        f"run_id={tmp_path.name}",
        "proxy_url=http://host.docker.internal:8765",
        "api=openai-completions",
        "reasoning=false",
        "max_tokens=49152",
        "context_window=262144",
    ]


def test_plan_tiers_are_configured_not_inferred() -> None:
    config = load_yaml()
    assert config["providers"]["kourier"]["plan_tier"] == "omega"
    assert config["providers"]["electronhub"]["plan_tier"] == "Coding Plan (DevPass)"


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
