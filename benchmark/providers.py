"""Provider registry operations: add, remove, use, edit.

Providers live in the user's registry (``~/.config/benching/providers.yaml``)
and are merged into the loaded config by ``benchmark.config.load_yaml``.
Credentials stay in per-provider env files under ``providers/`` with
restrictive permissions — never in the YAML itself.
"""
import os
import re
from pathlib import Path
from typing import Any

from benchmark.config import load_yaml
from benchmark.state import providers_dir, providers_registry_path, update_state

ENV_TEMPLATE = """# Credentials for {name} (chmod 600).
{auth_env}={api_key}
"""


def _load_registry() -> dict[str, Any]:
    import yaml

    path = providers_registry_path()
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("providers") if isinstance(data, dict) else {}


def _save_registry(providers: dict[str, Any]) -> None:
    import yaml

    path = providers_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"providers": providers}, sort_keys=True), encoding="utf-8")


def _auth_env_name(name: str) -> str:
    return name.upper().replace("-", "_") + "_API_KEY"


def provider_entry(
    name: str,
    base_url: str,
    api_model: str,
    api_key: str,
    api: str = "openai-completions",
    strict_model_check: bool = False,
) -> tuple[dict[str, Any], str]:
    """Build a registry entry + the env file body."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise SystemExit("provider name must contain only letters, numbers, '-' or '_'")
    if any("\n" in value or "\r" in value for value in (base_url, api_model, api_key)):
        raise SystemExit("provider fields must not contain newlines")
    if not base_url.strip() or not api_model.strip() or not api_key.strip():
        raise SystemExit("base URL, model, and API key are required")
    auth_env = _auth_env_name(name)
    entry = {
        "enabled": True,
        "env_file": str(providers_dir() / f"{name}.env"),
        "auth_env": auth_env,
        "base_url": base_url.rstrip("/"),
        "default_model": api_model,
        "api": api,
        "strict_model_check": strict_model_check,
    }
    return entry, ENV_TEMPLATE.format(name=name, auth_env=auth_env, api_key=api_key)


def add_provider(name: str, base_url: str, api_model: str, api_key: str, api: str = "openai-completions", strict_model_check: bool = False, make_active: bool = True) -> dict[str, Any]:
    """Register a provider, write its credential file, and optionally activate it.

    Raises ``SystemExit`` on conflict or invalid input.
    """
    if not name.strip() or "/" in name or ":" in name:
        raise SystemExit("provider name must be non-empty without '/' or ':'")
    if _load_registry().get(name):
        raise SystemExit(f"provider already exists: {name}")
    entry, env_body = provider_entry(name, base_url, api_model, api_key, api, strict_model_check)
    providers = _load_registry()
    providers[name] = entry
    _save_registry(providers)
    env_path = Path(entry["env_file"])
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(env_body, encoding="utf-8")
    os.chmod(env_path, 0o600)
    if make_active:
        update_state(active_provider=name)
    return entry


def remove_provider(name: str, forget_key_file: bool = True) -> None:
    """Unregister a provider; delete its credential file unless told not to."""
    providers = _load_registry()
    if name not in providers:
        raise SystemExit(f"unknown provider: {name}")
    entry = providers.pop(name)
    _save_registry(providers)
    env_file = Path(str(entry.get("env_file", "")))
    if forget_key_file and env_file.is_file():
        env_file.unlink()
    from benchmark.state import load_state, save_state

    state = load_state()
    if state.active_provider == name:
        state.active_provider = None
        save_state(state)


def update_provider(name: str, **changes: Any) -> dict[str, Any]:
    """Edit provider metadata; credentials stay in its env file."""
    providers = _load_registry()
    if name not in providers:
        raise SystemExit(f"unknown provider: {name}")
    entry = providers[name]
    editable = {"base_url", "default_model", "api", "strict_model_check", "plan", "plan_tier"}
    unknown = [key for key in changes if key not in editable]
    if unknown:
        raise SystemExit(f"cannot edit field(s): {', '.join(unknown)}")
    entry.update(changes)
    providers[name] = entry
    _save_registry(providers)
    return entry


def set_active_provider(name: str) -> dict[str, Any]:
    """Make ``name`` the active provider (must exist in the merged config)."""
    root = load_yaml()
    providers = root.get("providers") or {}
    if name not in providers:
        raise SystemExit(f"unknown provider: {name} (known: {', '.join(sorted(providers)) or 'none'})")
    update_state(active_provider=name)
    return providers[name]


def list_providers() -> list[dict[str, Any]]:
    """Registry entries plus repo-config providers, merged view for listing."""
    merged = dict(load_yaml().get("providers") or {})
    return [{"name": name, "cfg": cfg} for name, cfg in sorted(merged.items())]



def validate_registered_provider(
    name: str,
    root_config: dict[str, Any] | None = None,
    model_override: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Validate a registered provider and persist its report."""
    from benchmark.benchmarks import active_root_config
    from benchmark.config import benchmark_spec, enabled_providers, provider_config
    from benchmark.validation import validate_provider, write_validation_report

    root = root_config or active_root_config()
    if name not in enabled_providers(root):
        raise SystemExit(f"provider is not enabled: {name}")
    _, config = provider_config(name, root)
    spec = benchmark_spec(root)
    result = validate_provider(name, spec, root, config, model_override=model_override)
    return result, write_validation_report(name, result)


def probe_registered_provider(
    name: str,
    stages: tuple[int, ...] = (2, 3, 5, 6),
    root_config: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Run the staged provider probe through the benchmark layer."""
    from benchmark.benchmarks import active_root_config
    from benchmark.config import benchmark_spec, enabled_providers
    from benchmark.concurrency import probe_provider

    root = root_config or active_root_config()
    if name not in enabled_providers(root):
        raise SystemExit(f"provider is not enabled: {name}")
    return probe_provider(name, benchmark_spec(root), root, stages=stages)

def rename_key_field(name: str, api_key: str) -> None:
    """Rotate a provider's API key (writes its credential file)."""
    providers = _load_registry()
    if name not in providers:
        raise SystemExit(f"unknown provider: {name}")
    entry = providers[name]
    auth_env = str(entry.get("auth_env", _auth_env_name(name)))
    env_path = Path(str(entry.get("env_file", "")))
    values: dict[str, str] = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and not key.strip().startswith("#"):
                values[key.strip()] = value
    values[auth_env] = api_key
    lines = [f"{key}={value}" for key, value in values.items()]
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
