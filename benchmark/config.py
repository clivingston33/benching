"""Configuration loading for the benching benchmark harness.

Pure data access: loads ``config/benchmark.yaml`` and turns it into a
:class:`BenchmarkSpec` plus typed helpers for the provider registry.
Raises ``SystemExit`` with a human message on invalid configuration so both
the CLI and embedded callers surface the same errors.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark._paths import CACHE_ROOT, CONFIG, ROOT, RUNS


@dataclass(frozen=True)
class BenchmarkSpec:
    name: str
    version: str
    model: str
    reasoning: str
    tasks_dir: Path
    expected_task_count: int | None
    smoke_tasks: tuple[str, ...]
    agent: str
    max_tokens: int
    context_window: int
    run_id_prefix: str
    tokenizer_repo: str
    tokenizer_revision: str
    tokenizer_env_override: str | None
    cache_dir: Path

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.version}".strip()


def load_yaml() -> dict[str, Any]:
    """Load and validate config/benchmark.yaml as a plain dict."""
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required; install the project dependencies first") from exc
    value = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("benchmark"), dict):
        raise SystemExit("invalid config/benchmark.yaml")
    return value


def benchmark_spec(config: dict[str, Any]) -> BenchmarkSpec:
    """Build the immutable suite identity from the config dict."""
    settings = config.get("benchmark") if isinstance(config.get("benchmark"), dict) else {}
    tokenizer = settings.get("tokenizer") if isinstance(settings.get("tokenizer"), dict) else {}
    tasks_dir = Path(str(settings.get("tasks_dir", "") or "")).expanduser()
    if not tasks_dir.is_absolute():
        tasks_dir = (ROOT / tasks_dir).resolve()
    smoke = settings.get("smoke_tasks") or []
    if isinstance(smoke, str):
        smoke = [smoke]
    smoke_tasks = tuple(str(item) for item in smoke if str(item).strip())
    expected = settings.get("expected_task_count")
    try:
        expected_count = int(expected) if expected not in (None, "", 0) else None
    except (TypeError, ValueError):
        expected_count = None
    tokenizer_repo = str(tokenizer.get("repo") or "").strip()
    tokenizer_revision = str(tokenizer.get("revision") or "").strip()
    if not tokenizer_repo or not tokenizer_revision:
        raise SystemExit("config/benchmark.yaml: benchmark.tokenizer.repo and revision are required")
    cache_dir = CACHE_ROOT / "tokenizers" / tokenizer_repo.replace("/", "--")
    return BenchmarkSpec(
        name=str(settings.get("name", "benchmark")).strip() or "benchmark",
        version=str(settings.get("version", "")).strip(),
        model=str(settings.get("model", "")).strip(),
        reasoning=str(settings.get("reasoning", "default")).strip() or "default",
        tasks_dir=tasks_dir,
        expected_task_count=expected_count,
        smoke_tasks=smoke_tasks,
        agent=str(settings.get("agent", "agents.instrumented_omp_agent:InstrumentedOmpAgent")).strip(),
        max_tokens=int(settings.get("max_tokens", 49152) or 49152),
        context_window=int(settings.get("context_window", 262144) or 262144),
        run_id_prefix=str(settings.get("run_id_prefix", "bench")).strip() or "bench",
        tokenizer_repo=tokenizer_repo,
        tokenizer_revision=tokenizer_revision,
        tokenizer_env_override=str(tokenizer.get("env_override") or "").strip() or None,
        cache_dir=cache_dir,
    )


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; comments and blanks ignored, quotes stripped."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def env_path(config: dict[str, Any]) -> Path:
    """Absolute path of a provider's credential env file."""
    env_file = config.get("env_file") if isinstance(config.get("env_file"), str) else ""
    path = Path(env_file).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def provider_env_values(name: str, config: dict[str, Any]) -> dict[str, str]:
    """All KEY=VALUE pairs from a provider's env file (may be empty)."""
    return _parse_env(env_path(config))


def enabled_providers(root_config: dict[str, Any]) -> list[str]:
    """Names of providers with ``enabled: true``."""
    providers = root_config.get("providers") if isinstance(root_config.get("providers"), dict) else {}
    return [name for name, cfg in providers.items() if isinstance(cfg, dict) and cfg.get("enabled")]


def provider_config(name: str, root_config: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(root_config, provider_config)`` for an enabled provider."""
    config = root_config or load_yaml()
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    value = providers.get(name)
    if not isinstance(value, dict) or not value.get("enabled", False):
        raise SystemExit(f"provider is not enabled: {name}")
    return config, value


def resolve(name: str, config: dict[str, Any], values: dict[str, str] | None = None) -> tuple[str, str]:
    """Resolve ``(endpoint, api_model)`` for a provider.

    Env-file values ``<NAME>_BASE_URL`` / ``<NAME>_API_MODEL`` take
    precedence over the YAML ``base_url`` / ``api_model`` keys.
    """
    values = values if values is not None else provider_env_values(name, config)
    prefix = name.upper().replace("-", "_")
    endpoint = values.get(f"{prefix}_BASE_URL") or config.get("base_url") or config.get("endpoint")
    api_model = values.get(f"{prefix}_API_MODEL") or config.get("api_model")
    if not isinstance(endpoint, str) or not endpoint:
        raise SystemExit(f"endpoint unresolved for {name}")
    if not isinstance(api_model, str) or not api_model:
        raise SystemExit(f"api_model unresolved for {name}")
    return endpoint.rstrip("/"), api_model


def all_provider_env_values(root_config: dict[str, Any]) -> dict[str, str]:
    """Merge env values across every enabled provider (shared tokenizer overrides)."""
    merged: dict[str, str] = {}
    for name in enabled_providers(root_config):
        _, config = provider_config(name, root_config)
        merged.update(provider_env_values(name, config))
    return merged


def environment(config: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, str]:
    """Process environment for subprocesses: repo on PYTHONPATH, keys injected."""
    env = os.environ.copy()
    env.update(values if values is not None else _parse_env(env_path(config)))
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + env.get("PATH", "")
    return env
