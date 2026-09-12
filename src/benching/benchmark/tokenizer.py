"""Tokenizer cache management for benchmark runs.

Exact local token counting requires a pinned tokenizer. The harness keeps a
read-only cache of the pinned repository and never re-downloads during runs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from benching.benchmark.config import BenchmarkSpec


def tokenizer_metadata(
    spec: BenchmarkSpec,
    values: dict[str, str] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the selected model tokenizer, if a local copy exists."""
    settings = settings or {}
    values = values or {}
    repo = str(settings.get("tokenizer_repo") or spec.tokenizer_repo)
    revision = str(settings.get("tokenizer_revision") or spec.tokenizer_revision)
    env_override = settings.get("tokenizer_env_override") or spec.tokenizer_env_override
    cache_dir = settings.get("cache_dir") or spec.cache_dir
    env_path = values.get(env_override) if env_override else None
    local_cache = Path(env_path).expanduser() if env_path else cache_dir
    if not isinstance(local_cache, Path):
        local_cache = Path(str(local_cache))
    available = (local_cache / "tokenizer.json").is_file() and (local_cache / "config.json").is_file() if local_cache.is_dir() else local_cache.is_file()
    return {
        "repo": repo or None,
        "revision": revision or None,
        "source": "huggingface" if available else "unavailable",
        "local_cache": str(local_cache),
    }


def ensure_tokenizer(spec: BenchmarkSpec, values: dict[str, str] | None = None) -> dict[str, Any]:
    metadata = tokenizer_metadata(spec, values)
    if not metadata["repo"] or not metadata["revision"]:
        raise SystemExit("no tokenizer configured for this model")
    if metadata["source"] == "huggingface":
        return metadata
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=str(metadata["repo"]),
            revision=str(metadata["revision"]),
            local_dir=metadata["local_cache"],
            allow_patterns=["tokenizer.json", "tokenizer_config.json", "config.json"],
        )
    except Exception as exc:
        raise SystemExit(f"tokenizer unavailable: {exc}") from exc
    metadata = tokenizer_metadata(spec, values)
    if metadata["source"] != "huggingface":
        raise SystemExit("tokenizer download completed without tokenizer.json")
    return metadata

def resolve_tokenizer_context(
    root: dict[str, Any] | None,
    spec: BenchmarkSpec,
    provider: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Resolve the same tokenizer identity/config the runner uses.

    Tokenizer status/prepare and actual execution must agree: with a
    provider this applies provider config → model override → model
    settings exactly as :func:`benching.benchmark.runner.run_one` does.
    Without a provider it falls back to the spec-level shared cache view.
    Never downloads; use :func:`ensure_tokenizer` for that.
    """
    from benching.benchmark.config import (
        all_provider_env_values,
        provider_config,
        provider_env_values,
        resolve,
        resolve_model_settings,
    )
    if provider:
        _, config = provider_config(provider, root)
        values = provider_env_values(provider, config)
        endpoint, api_model = resolve(provider, config, values, model_override)
        model_settings = resolve_model_settings(config, spec, api_model, bool(model_override))
        return {
            "provider": provider,
            "endpoint": endpoint,
            "api_model": api_model,
            "values": values,
            "model_settings": model_settings,
            "metadata": tokenizer_metadata(spec, values, model_settings),
        }
    values = all_provider_env_values(root or {})
    return {
        "provider": None,
        "endpoint": None,
        "api_model": None,
        "values": values,
        "model_settings": {},
        "metadata": tokenizer_metadata(spec, values),
    }

def tokenizer_cache_path(metadata: dict[str, Any]) -> str | None:
    path = metadata.get("local_cache")
    return str(path) if isinstance(path, str) and path else None

