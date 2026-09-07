from __future__ import annotations

from pathlib import Path

from benchmark.benchmarks import active_root_config, add_benchmark, list_benchmarks, remove_benchmark, set_active_benchmark
from benchmark.config import enabled_providers, load_yaml, provider_env_values, resolve
from benchmark.providers import add_provider, remove_provider, set_active_provider, update_provider
from benchmark.state import load_state, update_state


def test_user_state_round_trip() -> None:
    state = update_state(active_provider="acme", concurrency=5, reasoning="enabled")
    assert state.active_provider == "acme"
    loaded = load_state()
    assert loaded.active_provider == "acme"
    assert loaded.concurrency == 5
    assert loaded.reasoning == "enabled"


def test_provider_registry_merges_and_removes(tmp_path: Path) -> None:
    add_provider("acme", "https://api.acme.test/v1", "acme-model", "secret")
    root = load_yaml()
    assert "acme" in enabled_providers(root)
    assert root["providers"]["acme"]["default_model"] == "acme-model"
    env_text = (tmp_path / "benching" / "providers" / "acme.env").read_text()
    assert "ACME_API_KEY=secret" in env_text
    assert "BASE_URL" not in env_text and "API_MODEL" not in env_text
    set_active_provider("acme")
    update_provider("acme", base_url="https://new-api.acme.test/v1", default_model="acme-model-v2")
    cfg = load_yaml()["providers"]["acme"]
    assert resolve("acme", cfg, provider_env_values("acme", cfg)) == ("https://new-api.acme.test/v1", "acme-model-v2")
    remove_provider("acme")
    assert "acme" not in (load_yaml().get("providers") or {})
    assert load_state().active_provider is None


def test_benchmark_registry_becomes_active_root(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "task-a").mkdir()
    path = add_benchmark(
        "my-suite",
        {
            "name": "My Suite",
            "version": "1.0",
            "tasks_dir": str(tasks),
            "agent": "agents.instrumented_omp_agent:InstrumentedOmpAgent",
            "model": "model-x",
            "reasoning": "default",
            "expected_task_count": 1,
            "smoke_tasks": ["task-a"],
            "tokenizer": {"repo": "org/tokenizer", "revision": "revision"},
        },
    )
    assert path.is_file()
    assert list_benchmarks()[0]["name"] == "my-suite"
    set_active_benchmark("my-suite")
    root = active_root_config()
    assert root["benchmark"]["name"] == "My Suite"
    assert load_state().active_benchmark == "my-suite"
    remove_benchmark("my-suite")
    assert not path.exists()
    assert load_state().active_benchmark is None


def test_shell_dispatch_persists_session_defaults() -> None:
    from cli.shell import Session, dispatch

    session = Session.from_state(load_state())
    assert dispatch(session, "/concurrency 7")
    assert dispatch(session, "/reasoning enabled")
    assert load_state().concurrency == 7
    assert load_state().reasoning == "enabled"
    assert not dispatch(session, "/exit")


def test_shell_provider_validation_failure_does_not_exit(monkeypatch) -> None:
    from cli.shell import Session, dispatch

    def fail(*args, **kwargs):
        raise SystemExit("provider unavailable")

    monkeypatch.setattr("benchmark.providers.validate_registered_provider", fail)
    session = Session.from_state(load_state())
    assert dispatch(session, "/provider validate acme")


def test_doctor_uses_active_benchmark(monkeypatch, tmp_path: Path) -> None:
    import benchmark.doctor as doctor

    tasks = tmp_path / "active-tasks"
    tasks.mkdir()
    (tasks / "task-a").mkdir()
    monkeypatch.setattr(
        doctor,
        "active_root_config",
        lambda: {
            "benchmark": {
                "name": "my-suite",
                "version": "1.0",
                "tasks_dir": str(tasks),
                "agent": "agents.instrumented_omp_agent:InstrumentedOmpAgent",
            }
        },
    )
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor, "tokenizer_metadata", lambda spec: {"source": "unavailable"})
    results = {item["name"]: item for item in doctor.checks()}
    assert results["Tasks"]["detail"] == "1 found"
    assert results["Tokenizer"]["detail"] == "not cached"
