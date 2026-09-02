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


def test_run_one_progress_hook_orders_preflight_phases(tmp_path, monkeypatch) -> None:
    """run_one reports deterministic preflight phases through the hook."""
    import benchmark.runner as runner

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(runner, "executable", lambda name: None)
    monkeypatch.setattr(runner, "start_proxy", lambda directory, port=8765: None)
    monkeypatch.setattr(runner, "stop_process", lambda process: None)
    monkeypatch.setattr(runner, "validate_provider", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr(runner, "task_names", lambda mode, spec: ["task-a"])
    monkeypatch.setattr(runner, "environment", lambda config, values=None: {})

    spec = make_spec(expected_task_count=None)
    monkeypatch.setattr(runner, "run_directory", lambda *args, **kwargs: _FakeRunDir(tmp_path))
    monkeypatch.setattr(runner, "harbor_command", lambda *args, **kwargs: ["true"])
    monkeypatch.setattr(runner, "tokenizer_metadata", lambda spec, values=None: {"source": "huggingface"})

    captured: dict = {}

    class _FakePopen:
        pid = 1234

        def __init__(self, command, **kwargs):
            captured["command"] = command

        def wait(self):
            return 0

    monkeypatch.setattr(runner.subprocess, "Popen", _FakePopen)

    config = {"benchmark": {"name": "suite", "version": "1", "model": "model-x", "reasoning": "default", "tasks_dir": "~/nonexistent/tasks", "smoke_tasks": ["task-a"], "tokenizer": {"repo": "org/t", "revision": "0123456789abcdef"}, "agent": "agents.instrumented_omp_agent:InstrumentedOmpAgent", "max_tokens": 1, "context_window": 2, "run_id_prefix": "bench"}}
    root = {"benchmark": config["benchmark"], "providers": {"acme": {"enabled": True, "env_file": str(tmp_path / "acme.env"), "auth_env": "ACME_API_KEY", "base_url": "https://api.acme.test/v1", "api_model": "acme-model-1"}}}
    (tmp_path / "acme.env").write_text("ACME_API_KEY=secret\n", encoding="utf-8")

    monkeypatch.setattr(runner, "load_yaml", lambda: root)
    monkeypatch.setattr(runner, "benchmark_spec", lambda config: make_spec(expected_task_count=None))
    monkeypatch.setattr(runner, "resolve", lambda name, config, values=None: ("https://api.acme.test/v1", "acme-model-1"))
    monkeypatch.setattr(runner, "provider_env_values", lambda name, config: {"ACME_API_KEY": "secret"})
    monkeypatch.setattr(runner, "provider_config", lambda name, root_config=None: (root, root["providers"]["acme"]))

    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: None)

    from benchmark.status import ProgressEvent

    def collect(event: ProgressEvent) -> None:
        calls.append((event.phase, event.message))

    runner.run_one(RunOptions(provider="acme", mode="full"), root, progress=collect)

    phases = [phase for phase, _ in calls]
    assert phases == ["docker", "tokenizer", "validate", "validate", "proxy", "running", "analyze", "done"]
    assert calls[0][1] == "docker available"
    assert calls[2][1] == "validating acme"
    assert calls[-1][1] == "run complete"


class _FakeRunDir:
    """Minimal stand-in for run_directory()'s returned Path."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def __truediv__(self, other: str) -> Path:
        return self._base / other

    def mkdir(self, *args, **kwargs) -> None:
        return None

    @property
    def name(self) -> str:
        return "fake-run"


