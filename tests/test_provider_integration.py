from __future__ import annotations

import json
from pathlib import Path

from benching.benchmark.config import BenchmarkSpec, benchmark_spec, load_yaml, resolve, resolve_model_settings
from benching.benchmark.runner import RunOptions, harbor_command
from benching.benchmark.validation import classify_validation, parse_stream_body


def make_spec(**overrides) -> BenchmarkSpec:
    values = dict(
        name="terminal-bench",
        version="2.1",
        model="model-x",
        reasoning="default",
        tasks_dir="~/task-suite/tasks",
        expected_task_count=2,
        smoke_tasks=("task-a",),
        agent="benching.agents.instrumented_omp_agent:InstrumentedOmpAgent",
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
    assert spec.model == ""
    assert spec.reasoning == "default"
    assert spec.tasks_dir.name == "tasks"
    assert spec.expected_task_count == 89
    assert len(spec.smoke_tasks) == 3
    assert spec.agent == "benching.agents.instrumented_omp_agent:InstrumentedOmpAgent"
    assert spec.max_tokens is None
    assert spec.context_window is None
    assert spec.run_id_prefix == "bench"
    assert spec.tokenizer_repo == ""
    assert spec.tokenizer_revision == ""
    assert spec.tokenizer_env_override is None


def test_config_ships_with_no_enabled_providers() -> None:
    config = load_yaml()
    providers = config.get("providers") or {}
    assert all(not (isinstance(cfg, dict) and cfg.get("enabled")) for cfg in providers.values())


def test_harbor_command_preserves_agent_kwargs(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

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
        proxy_auth_token="test-token",
    )
    kwargs = [command[index + 1] for index, value in enumerate(command) if value == "--agent-kwarg"]
    assert kwargs == [
        "provider=acme",
        "provider_plan=",
        "benchmark_model=acme-model-1",
        "model=acme-model-1",
        "upstream=https://api.acme.test/v1",
        "api_key_env=ACME_API_KEY",
        f"run_id={tmp_path.name}",
        "proxy_url=http://host.docker.internal:8765",
        "proxy_auth_token=test-token",
        "api=openai-completions",
        "reasoning=default",
        "max_tokens=49152",
        "context_window=262144",
    ]
    assert "--path" in command
    assert command[command.index("--path") + 1] == str(spec.tasks_dir)
    assert "deepseek" not in " ".join(command).lower()


def test_resolve_uses_registry_metadata_and_run_override() -> None:
    config = {"base_url": "https://api.acme.test/v1", "default_model": "acme-model-1", "api_model": "legacy-model"}
    endpoint, api_model = resolve("acme", config, {"ACME_BASE_URL": "https://old.test", "ACME_API_MODEL": "old-model"})
    assert endpoint == "https://api.acme.test/v1"
    assert api_model == "acme-model-1"
    assert resolve("acme", config, {}, "new-model") == ("https://api.acme.test/v1", "new-model")


def test_provider_model_defaults_override_benchmark_execution_defaults() -> None:
    spec = make_spec(tokenizer_repo="", tokenizer_revision="", max_tokens=None, context_window=None)
    settings = resolve_model_settings(
        {
            "default_model": "provider-model",
            "model_defaults": {
                "tokenizer": {"repo": "org/provider-tokenizer", "revision": "revision"},
                "max_tokens": 8192,
                "context_window": 65536,
            },
        },
        spec,
        "selected-model",
        model_override=True,
    )
    assert settings["model"] == "selected-model"
    assert settings["max_tokens"] == 8192
    assert settings["context_window"] == 65536
    assert settings["tokenizer_repo"] == "org/provider-tokenizer"
    assert settings["sources"]["model"] == "run.model_override"
    assert settings["sources"]["tokenizer"] == "provider.model_defaults"




def test_run_metadata_records_effective_setting_sources(tmp_path, monkeypatch) -> None:
    import benching.benchmark.runner as runner

    monkeypatch.setattr(runner, "runs_root", lambda: tmp_path)
    spec = make_spec(tokenizer_repo="", tokenizer_revision="", max_tokens=None, context_window=None)
    settings = resolve_model_settings(
        {"default_model": "provider-model", "model_defaults": {"max_tokens": 8192}},
        spec,
        "selected-model",
        model_override=True,
    )
    directory = runner.run_directory(
        RunOptions(provider="acme", mode="smoke", benchmark_model="selected-model"),
        spec,
        {"plan": None, "plan_tier": "unknown"},
        "https://api.acme.test/v1",
        "selected-model",
        ["task-a"],
        model_settings=settings,
    )
    run = json.loads((directory / "run.json").read_text())
    assert run["model"] == "selected-model"
    assert run["effective_settings"]["max_tokens"] == 8192
    assert run["effective_settings"]["sources"]["model"] == "run.model_override"
    assert run["effective_settings"]["sources"]["context_window"] == "harbor.default"


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
    import benching.benchmark.runner as runner

    calls: list[tuple[str, str]] = []
    # Orchestration mechanics under test with mocked children; real benchmark
    # execution still requires Linux/WSL (see benchmark.lifecycle).
    monkeypatch.setenv("BENCHING_ALLOW_UNSUPPORTED_PLATFORM", "1")
    monkeypatch.setattr(runner, "executable", lambda name: None)
    monkeypatch.setattr(runner, "start_proxy", lambda directory, port=8765, auth_token="", timeout=10.0: None)
    monkeypatch.setattr(runner, "validate_provider", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr(runner, "task_names", lambda mode, spec: ["task-a"])
    monkeypatch.setattr(runner, "environment", lambda config, values=None: {})

    monkeypatch.setattr(runner, "tokenizer_metadata", lambda *args, **kwargs: {"source": "unavailable"})
    monkeypatch.setattr(runner, "harbor_command", lambda *args, **kwargs: ["true"])

    captured: dict = {}

    class _FakePopen:
        pid = 1234

        def __init__(self, command, **kwargs):
            captured["command"] = command

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(runner, "spawn_owned", _FakePopen)

    config = {"benchmark": {"name": "suite", "version": "1", "model": "model-x", "reasoning": "default", "tasks_dir": "~/nonexistent/tasks", "smoke_tasks": ["task-a"], "tokenizer": {"repo": "org/t", "revision": "0123456789abcdef"}, "agent": "benching.agents.instrumented_omp_agent:InstrumentedOmpAgent", "max_tokens": 1, "context_window": 2, "run_id_prefix": "bench"}}
    root = {"benchmark": config["benchmark"], "providers": {"acme": {"enabled": True, "env_file": str(tmp_path / "acme.env"), "auth_env": "ACME_API_KEY", "base_url": "https://api.acme.test/v1", "api_model": "acme-model-1"}}}
    (tmp_path / "acme.env").write_text("ACME_API_KEY=secret\n", encoding="utf-8")

    monkeypatch.setattr(runner, "resolve", lambda *args, **kwargs: ("https://api.acme.test/v1", "acme-model-1"))
    monkeypatch.setattr(runner, "benchmark_spec", lambda config: make_spec(expected_task_count=None))
    monkeypatch.setattr(runner, "provider_env_values", lambda name, config: {"ACME_API_KEY": "secret"})
    monkeypatch.setattr(runner, "provider_config", lambda name, root_config=None: (root, root["providers"]["acme"]))

    def _fake_analyze(*args, **kwargs):
        """Emulate successful canonical analysis publication."""
        command = args[0]
        run_dir = Path(command[-1])
        (run_dir / "metrics.jsonl").write_text('{"value": 1}\n', encoding="utf-8")
        (run_dir / "summary.json").write_text('{"schema_version": 1}\n', encoding="utf-8")

    monkeypatch.setattr(runner.subprocess, "run", _fake_analyze)
    monkeypatch.setattr(runner, "version", lambda name: None)

    from benching.benchmark.status import ProgressEvent

    def collect(event: ProgressEvent) -> None:
        calls.append((event.phase, event.message))
    runner.run_one(RunOptions(provider="acme", mode="full", benchmark_model="other-model", reasoning="enabled"), root, progress=collect)

    phases = [phase for phase, _ in calls]
    assert phases == ["docker", "tokenizer", "validate", "validate", "proxy", "running", "analyze", "done"]
    assert calls[0][1] == "docker available"
    assert calls[1][1] == "tokenizer unavailable; provider token counts retained"
    assert calls[2][1] == "validating acme"

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



