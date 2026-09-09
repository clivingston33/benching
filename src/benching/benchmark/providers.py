"""Provider registry operations: add, remove, use, edit.

Providers live in the user's registry (``~/.config/benching/providers.yaml``)
and are merged into the loaded config by ``benching.benchmark.config.load_yaml``.
Credentials stay in per-provider env files under ``providers/`` with
restrictive permissions — never in the YAML itself.
"""
from pathlib import Path
from typing import Any

from benching.benchmark.config import load_yaml
from benching.benchmark.security import (
    is_owned_credential_file,
    validate_api_key,
    validate_endpoint,
    validate_model_name,
    validate_registry_name,
    write_credential_file,
)
from benching.benchmark.state import providers_dir, providers_registry_path, update_state

ENV_TEMPLATE = """# Credentials for {name} (chmod 600).
{auth_env}={api_key}
"""


def _load_registry() -> dict[str, Any]:
    import yaml

    from benching.benchmark.io import yaml_error_summary

    path = providers_registry_path()
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SystemExit(f"invalid provider registry: {path} ({yaml_error_summary(exc)})") from None
    if not isinstance(data, dict):
        raise SystemExit(f"invalid provider registry: {path} (expected a mapping)")
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        raise SystemExit(f"invalid provider registry: {path} (expected providers mapping)")
    return providers


def _save_registry(providers: dict[str, Any]) -> None:
    """Persist the provider registry with atomic replacement.

    Simultaneous mutation from multiple processes is NOT supported:
    concurrent writers get last-writer-wins on complete documents, never
    torn files. See README for the policy.
    """
    from benching.benchmark.io import dump_yaml_atomic

    dump_yaml_atomic(providers_registry_path(), {"providers": providers}, sort_keys=True)


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
    """Build a registry entry + the env file body.

    Uses the shared security boundary so add/edit/rotate reject
    equivalent invalid input. Never echoes secrets in errors.
    """
    validate_registry_name(name, "provider")
    if not isinstance(base_url, str) or not base_url.strip():
        raise SystemExit("base URL, model, and API key are required")
    normalized_url = validate_endpoint(base_url)
    validated_model = validate_model_name(api_model)
    validate_api_key(api_key)
    auth_env = _auth_env_name(name)
    entry = {
        "enabled": True,
        "env_file": str(providers_dir() / f"{name}.env"),
        "auth_env": auth_env,
        "base_url": normalized_url,
        "default_model": validated_model,
        "api": api,
        "strict_model_check": strict_model_check,
    }
    return entry, ENV_TEMPLATE.format(name=name, auth_env=auth_env, api_key=api_key)


def add_provider(name: str, base_url: str, api_model: str, api_key: str, api: str = "openai-completions", strict_model_check: bool = False, make_active: bool = True) -> dict[str, Any]:
    """Register a provider, write its credential file, and optionally activate it.

    Validates first, writes the credential file before publishing registry
    metadata, and never leaves a half-registered provider when credential
    establishment fails. Raises ``SystemExit`` on conflict or invalid input.
    """
    validate_registry_name(name, "provider")
    if _load_registry().get(name):
        raise SystemExit(f"provider already exists: {name}")
    # Validate everything before mutating any state.
    entry, env_body = provider_entry(name, base_url, api_model, api_key, api, strict_model_check)
    env_path = Path(entry["env_file"])
    existed_before = env_path.is_file()
    # Sensitive material first; registry metadata only after it is safely stored.
    write_credential_file(env_path, env_body)
    try:
        providers = _load_registry()
        if providers.get(name):
            raise SystemExit(f"provider already exists: {name}")
        providers[name] = entry
        _save_registry(providers)
    except BaseException:
        # Roll back the credential file we just created so a failed
        # registration does not leave an orphan secret without metadata.
        # Pre-existing files are left untouched.
        if not existed_before and env_path.is_file():
            try:
                env_path.unlink()
            except OSError:
                pass
        raise
    if make_active:
        update_state(active_provider=name)
    return entry


def remove_provider(name: str, forget_key_file: bool = True) -> None:
    """Unregister a provider; delete only application-owned credential files.

    Files under the application providers directory may be removed as part
    of provider removal. Externally supplied env files outside that
    directory are never silently deleted.
    """
    validate_registry_name(name, "provider")
    providers = _load_registry()
    if name not in providers:
        raise SystemExit(f"unknown provider: {name}")
    entry = providers.pop(name)
    _save_registry(providers)
    if forget_key_file:
        raw = str(entry.get("env_file", ""))
        if raw:
            env_file = Path(raw)
            if env_file.is_file() and is_owned_credential_file(env_file, providers_dir()):
                env_file.unlink()
    from benching.benchmark.state import load_state, save_state

    state = load_state()
    if state.active_provider == name:
        state.active_provider = None
        save_state(state)


def update_provider(name: str, **changes: Any) -> dict[str, Any]:
    """Edit provider metadata; credentials stay in its env file.

    Validates all changes before persisting so an invalid edit cannot
    leave a partially valid configuration. Endpoint/model edits use the
    same boundary as registration.
    """
    validate_registry_name(name, "provider")
    providers = _load_registry()
    if name not in providers:
        raise SystemExit(f"unknown provider: {name}")
    editable = {"base_url", "default_model", "model_defaults", "api", "strict_model_check", "plan", "plan_tier"}
    unknown = [key for key in changes if key not in editable]
    if unknown:
        raise SystemExit(f"cannot edit field(s): {', '.join(unknown)}")
    # Validate first; do not mutate the stored entry until all checks pass.
    validated: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "base_url":
            if not isinstance(value, str) or not value.strip():
                raise SystemExit("base URL is required")
            validated[key] = validate_endpoint(value)
        elif key == "default_model":
            validated[key] = validate_model_name(value)
        else:
            validated[key] = value
    entry = dict(providers[name])
    entry.update(validated)
    providers[name] = entry
    _save_registry(providers)
    return entry


def set_active_provider(name: str) -> dict[str, Any]:
    """Make ``name`` the active provider (must exist in the merged config)."""
    validate_registry_name(name, "provider")
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
    from benching.benchmark.benchmarks import active_root_config
    from benching.benchmark.config import benchmark_spec, enabled_providers, provider_config
    from benching.benchmark.validation import validate_provider, write_validation_report

    validate_registry_name(name, "provider")
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
    from benching.benchmark.benchmarks import active_root_config
    from benching.benchmark.config import benchmark_spec, enabled_providers
    from benching.benchmark.concurrency import probe_provider

    validate_registry_name(name, "provider")
    root = root_config or active_root_config()
    if name not in enabled_providers(root):
        raise SystemExit(f"provider is not enabled: {name}")
    return probe_provider(name, benchmark_spec(root), root, stages=stages)

def rename_key_field(name: str, api_key: str) -> None:
    """Rotate a provider's API key (writes its credential file).

    Applies the same key validation as initial registration so rotation
    rejects newline/control injection. Validates before touching files.
    """
    validate_registry_name(name, "provider")
    validate_api_key(api_key)
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
    write_credential_file(env_path, "\n".join(lines) + "\n")

