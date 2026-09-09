"""Configuration loading for the benching benchmark harness.

Pure data access: loads the packaged default benchmark manifest and turns
it into a :class:`BenchmarkSpec` plus typed helpers for the provider
registry. The packaged default is an immutable starting point; user
changes live in the user-local config/state mechanism, never in the
package. Raises ``SystemExit`` with a human message on invalid
configuration so both the CLI and embedded callers surface the same
errors.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benching.benchmark._paths import CACHE_ROOT, package_parent, resource_text
from benching.benchmark.state import providers_registry_path


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
    max_tokens: int | None
    context_window: int | None
    run_id_prefix: str
    tokenizer_repo: str
    tokenizer_revision: str
    tokenizer_env_override: str | None
    cache_dir: Path

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.version}".strip()


def default_config_text() -> str:
    """Raw text of the packaged immutable default benchmark manifest."""
    return resource_text("resources", "benchmark.yaml")


def load_yaml(path: Path | None = None) -> dict[str, Any]:
    """Load and validate a benchmark config file as a plain dict.

    Defaults to the packaged default manifest with the user provider
    registry (~/.config/benching/providers.yaml) merged on top. An
    explicit path is used verbatim and never merged.
    """
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required; install the project dependencies first") from exc
    if path is None:
        value = yaml.safe_load(default_config_text())
        source = "packaged default benchmark"
    else:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        source = str(path)
    if not isinstance(value, dict) or not isinstance(value.get("benchmark"), dict):
        raise SystemExit(f"invalid benchmark config: {source}")
    if path is None:
        _merge_user_providers(value, yaml)
    return value


def _merge_user_providers(root: dict[str, Any], yaml: Any) -> None:
    """Overlay user-registered providers on the repo registry."""
    registry = providers_registry_path()
    if not registry.is_file():
        return
    user = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    providers = user.get("providers") if isinstance(user, dict) else None
    if isinstance(providers, dict):
        merged = root.setdefault("providers", {})
        merged.update({name: cfg for name, cfg in providers.items() if isinstance(cfg, dict)})


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def benchmark_spec(config: dict[str, Any]) -> BenchmarkSpec:
    """Build benchmark identity and optional execution defaults."""
    settings = config.get("benchmark") if isinstance(config.get("benchmark"), dict) else {}
    tokenizer = settings.get("tokenizer") if isinstance(settings.get("tokenizer"), dict) else {}
    tasks_dir = Path(str(settings.get("tasks_dir", "") or "")).expanduser()
    if not tasks_dir.is_absolute():
        tasks_dir = (Path.cwd() / tasks_dir).resolve()
    smoke = settings.get("smoke_tasks") or []
    if isinstance(smoke, str):
        smoke = [smoke]
    smoke_tasks = tuple(str(item) for item in smoke if str(item).strip())
    expected = settings.get("expected_task_count")
    expected_count = _optional_int(expected) if expected not in (None, "", 0) else None
    tokenizer_repo = str(tokenizer.get("repo") or "").strip()
    tokenizer_revision = str(tokenizer.get("revision") or "").strip()
    cache_dir = CACHE_ROOT / "tokenizers" / (tokenizer_repo.replace("/", "--") if tokenizer_repo else "unconfigured")
    return BenchmarkSpec(
        name=str(settings.get("name", "benchmark")).strip() or "benchmark",
        version=str(settings.get("version", "")).strip(),
        model=str(settings.get("model", "")).strip(),
        reasoning=str(settings.get("reasoning", "default")).strip() or "default",
        tasks_dir=tasks_dir,
        expected_task_count=expected_count,
        smoke_tasks=smoke_tasks,
        agent=str(settings.get("agent", "benching.agents.instrumented_omp_agent:InstrumentedOmpAgent")).strip(),
        max_tokens=_optional_int(settings.get("max_tokens")),
        context_window=_optional_int(settings.get("context_window")),
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
    """Absolute path of a provider's credential env file.

    Relative paths resolve against the invoking working directory, never
    the package installation directory.
    """
    env_file = config.get("env_file") if isinstance(config.get("env_file"), str) else ""
    path = Path(env_file).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
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
    from benching.benchmark.security import validate_registry_name

    validate_registry_name(name, "provider")
    config = root_config or load_yaml()
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    value = providers.get(name)
    if not isinstance(value, dict) or not value.get("enabled", False):
        raise SystemExit(f"provider is not enabled: {name}")
    return config, value


def resolve(
    name: str,
    config: dict[str, Any],
    values: dict[str, str] | None = None,
    model_override: str | None = None,
) -> tuple[str, str]:
    """Resolve the endpoint and selected provider model.

    Endpoint and model metadata live in the provider registry. Credential env
    files intentionally contain secrets only; ``model_override`` is the
    per-run/session model selection.

    Uses the shared :mod:`benchmark.security` boundary so every caller
    (add/edit/resolve/preflight/probe/run) rejects equivalent invalid
    endpoints/models consistently before any credential is transmitted.
    """
    from benching.benchmark.security import validate_endpoint, validate_model_name

    endpoint = config.get("base_url") or config.get("endpoint")
    api_model = model_override or config.get("default_model") or config.get("api_model")
    if not isinstance(endpoint, str) or not endpoint:
        raise SystemExit(f"endpoint unresolved for {name}")
    if not isinstance(api_model, str) or not api_model:
        raise SystemExit(f"default model unresolved for {name}")
    try:
        normalized_endpoint = validate_endpoint(endpoint)
    except SystemExit as exc:
        # Preserve provider context without echoing a possibly
        # credential-bearing URL.
        raise SystemExit(f"invalid endpoint for {name}: {exc.code or exc}") from None
    try:
        validated_model = validate_model_name(api_model)
    except SystemExit as exc:
        raise SystemExit(f"invalid model for {name}: {exc.code or exc}") from None
    return normalized_endpoint, validated_model


def resolve_model_settings(
    config: dict[str, Any],
    spec: BenchmarkSpec,
    model: str,
    model_override: bool = False,
) -> dict[str, Any]:
    """Resolve model-specific execution settings and their provenance."""
    defaults = config.get("model_defaults") if isinstance(config.get("model_defaults"), dict) else {}
    tokenizer = defaults.get("tokenizer") if isinstance(defaults.get("tokenizer"), dict) else {}
    repo = str(tokenizer.get("repo") or spec.tokenizer_repo).strip()
    revision = str(tokenizer.get("revision") or spec.tokenizer_revision).strip()
    env_override = str(tokenizer.get("env_override") or spec.tokenizer_env_override or "").strip() or None
    cache_dir = CACHE_ROOT / "tokenizers" / (repo.replace("/", "--") if repo else "unconfigured")
    provider_model_source = "provider.default_model" if config.get("default_model") else "provider.api_model"
    return {
        "model": model,
        "sources": {
            "model": "run.model_override" if model_override else provider_model_source,
            "endpoint": "provider.base_url" if config.get("base_url") else "provider.endpoint",
            "reasoning": "run.reasoning_setting",
            "tokenizer": "provider.model_defaults" if tokenizer else ("benchmark.tokenizer" if repo else "unconfigured"),
            "max_tokens": "provider.model_defaults" if "max_tokens" in defaults else ("benchmark.max_tokens" if spec.max_tokens is not None else "harbor.default"),
            "context_window": "provider.model_defaults" if "context_window" in defaults else ("benchmark.context_window" if spec.context_window is not None else "harbor.default"),
        },
        "tokenizer_repo": repo,
        "tokenizer_revision": revision,
        "tokenizer_env_override": env_override,
        "cache_dir": cache_dir,
        "max_tokens": _optional_int(defaults.get("max_tokens")) if "max_tokens" in defaults else spec.max_tokens,
        "context_window": _optional_int(defaults.get("context_window")) if "context_window" in defaults else spec.context_window,
    }


def all_provider_env_values(root_config: dict[str, Any]) -> dict[str, str]:
    """Merge env values across every enabled provider (shared tokenizer overrides)."""
    merged: dict[str, str] = {}
    for name in enabled_providers(root_config):
        _, config = provider_config(name, root_config)
        merged.update(provider_env_values(name, config))
    return merged


def environment(config: dict[str, Any], values: dict[str, str] | None = None) -> dict[str, str]:
    """Child-process environment: keys injected, package importable, local tools visible.

    Everything is scoped to the returned mapping; the parent process
    environment is never modified. The directory containing the imported
    ``benching`` package goes on the child's PYTHONPATH, which keeps both
    source-checkout and installed subprocesses importable without global
    mutation. ``~/.local/bin`` is prepended for the child only so
    user-local harbor/omp resolve there.
    """
    env = os.environ.copy()
    env.update(values if values is not None else _parse_env(env_path(config)))
    parent = str(package_parent())
    env["PYTHONPATH"] = parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + env.get("PATH", "")
    return env

