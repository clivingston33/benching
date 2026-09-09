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


def tokenizer_cache_path(metadata: dict[str, Any]) -> str | None:
    path = metadata.get("local_cache")
    return str(path) if isinstance(path, str) and path else None

