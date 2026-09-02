from __future__ import annotations

from pathlib import Path

from benchmark.config import BenchmarkSpec, benchmark_spec, load_yaml, resolve
from benchmark.runner import RunOptions, harbor_command
from benchmark.validation import classify_validation, parse_stream_body


def make_spec(**overrides) -> BenchmarkSpec:
    values = dict(
        name="terminal-bench",
        version="2.1",
        model="model-x",
        reasoning="default",
        tasks_dir="~/task-suite/tasks",
        expected_task_count=2,
        smoke_tasks=("task-a",),
        agent="agents.instrumented_omp_agent:InstrumentedOmpAgent",
        max_tokens=49152,
        context_window=262144,
        run_id_prefix="bench",
        tokenizer_repo="org/tokenizer",
        tokenizer_revision="rev123",
        tokenizer_env_override=None,
        cache_dir=Path("/tmp/cache"),
    )
    values.update(overrides)
    return BenchmarkSpec(**values)


def test_benchmark_spec_reads_full_identity_from_config() -> None:
    config = load_yaml()
    spec = benchmark_spec(config)
    assert spec.name == "terminal-bench"
    assert spec.version == "2.1"
    assert spec.model == "deepseek-v4-flash-0731"
    assert spec.reasoning == "default"
    assert spec.tasks_dir.name == "tasks"
    assert spec.expected_task_count == 89
    assert len(spec.smoke_tasks) == 3
    assert spec.agent == "agents.instrumented_omp_agent:InstrumentedOmpAgent"
    assert spec.max_tokens > 0
    assert spec.context_window > 0
    assert spec.run_id_prefix == "bench"
    assert spec.tokenizer_repo.startswith("deepseek-ai/")
    assert len(spec.tokenizer_revision) == 40
    assert spec.tokenizer_env_override == "TOKENIZER_PATH"


def test_config_ships_with_no_enabled_providers() -> None:
    config = load_yaml()
    providers = config.get("providers") or {}
    assert all(not (isinstance(cfg, dict) and cfg.get("enabled")) for cfg in providers.values())


def test_harbor_command_preserves_agent_kwargs(tmp_path, monkeypatch) -> None:
    import benchmark.runner as runner

    monkeypatch.setattr(runner, "executable", lambda name: name)
    spec = make_spec(expected_task_count=None)
    command = harbor_command(
        RunOptions("acme", "smoke"),
        spec,
        {"auth_env": "ACME_API_KEY", "api": "openai-completions", "plan": None},
        "https://api.acme.test/v1",
        "acme-model-1",
        tmp_path,
        ["task-a"],
    )
    kwargs = [command[index + 1] for index, value in enumerate(command) if value == "--agent-kwarg"]
    assert kwargs == [
        "provider=acme",
        "provider_plan=",
        "benchmark_model=model-x",
        "model=acme-model-1",
        "upstream=https://api.acme.test/v1",
        "api_key_env=ACME_API_KEY",
        f"run_id={tmp_path.name}",
        "proxy_url=http://host.docker.internal:8765",
        "api=openai-completions",
        "reasoning=default",
        "max_tokens=49152",
        "context_window=262144",
    ]
    assert "--path" in command
    assert command[command.index("--path") + 1] == str(spec.tasks_dir)
    assert "deepseek" not in " ".join(command).lower()


def test_resolve_uses_configured_api_model() -> None:
    endpoint, api_model = resolve("acme", {"base_url": "https://api.acme.test/v1", "api_model": "acme-model-1"}, {})
    assert endpoint == "https://api.acme.test/v1"
    assert api_model == "acme-model-1"


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
