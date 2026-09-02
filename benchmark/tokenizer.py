"""Tokenizer cache management for benchmark runs.

Exact local token counting requires a pinned tokenizer. The harness keeps a
read-only cache of the pinned repository and never re-downloads during runs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from benchmark._paths import CACHE_ROOT
from benchmark.config import BenchmarkSpec


def tokenizer_metadata(spec: BenchmarkSpec, values: dict[str, str] | None = None) -> dict[str, Any]:
    """Describe where the tokenizer resolves (local cache or env override).

    The optional env override names a tokenizer.json (file) or a directory
    containing one plus config.json, shared across providers.
    """
    values = values or {}
    env_path = values.get(spec.tokenizer_env_override) if spec.tokenizer_env_override else None
    local_cache = Path(env_path).expanduser() if env_path else spec.cache_dir
    if not isinstance(local_cache, Path):
        local_cache = spec.cache_dir
    available = (local_cache / "tokenizer.json").is_file() and (local_cache / "config.json").is_file() if local_cache.is_dir() else local_cache.is_file()
    return {
        "repo": spec.tokenizer_repo,
        "revision": spec.tokenizer_revision,
        "source": "huggingface" if available else "unavailable",
        "local_cache": str(local_cache),
    }


def ensure_tokenizer(spec: BenchmarkSpec, values: dict[str, str] | None = None) -> dict[str, Any]:
    """Download the pinned tokenizer into the local cache if not present."""
    metadata = tokenizer_metadata(spec, values)
    if metadata["source"] == "huggingface":
        return metadata
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=spec.tokenizer_repo,
            revision=spec.tokenizer_revision,
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
