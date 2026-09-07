"""Persistent benching user state (``~/.config/benching/config.yaml``).

The repository's ``config/benchmark.yaml`` stays the shared suite + provider
registry; this file is the user's own state: the active provider/benchmark
and the default run knobs. API keys never live here — they stay in
per-provider credential files.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from benchmark._paths import DEFAULT_CONCURRENCY, DEFAULT_TRIALS


def app_dir() -> Path:
    """User config root (overridable via ``BENCHING_CONFIG_DIR`` for tests)."""
    override = os.environ.get("BENCHING_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "benching"


def config_path() -> Path:
    return app_dir() / "config.yaml"


def providers_dir() -> Path:
    return app_dir() / "providers"


def benchmarks_dir() -> Path:
    return app_dir() / "benchmarks"


@dataclass
class UserState:
    active_provider: str | None = None
    active_benchmark: str | None = None
    model: str | None = None
    concurrency: int = DEFAULT_CONCURRENCY
    trials: int = DEFAULT_TRIALS
    reasoning: str = "default"


def providers_registry_path() -> Path:
    return app_dir() / "providers.yaml"


def _str_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def load_state() -> UserState:
    """Load user state; a missing file or keys fall back to defaults."""
    path = config_path()
    if not path.is_file():
        return UserState()
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required; install the project dependencies first") from exc
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise SystemExit(f"invalid benching config: {path}")
    try:
        concurrency = int(raw.get("concurrency", DEFAULT_CONCURRENCY) or DEFAULT_CONCURRENCY)
        trials = int(raw.get("trials", DEFAULT_TRIALS) or DEFAULT_TRIALS)
    except (TypeError, ValueError):
        raise SystemExit(f"invalid benching config: {path}")
    reasoning = str(raw.get("reasoning") or "default")
    if concurrency < 1 or trials < 1 or reasoning not in {"default", "enabled", "disabled"}:
        raise SystemExit(f"invalid benching config: {path}")
    return UserState(
        active_provider=_str_or_none(raw.get("active_provider")),
        active_benchmark=_str_or_none(raw.get("active_benchmark")),
        model=_str_or_none(raw.get("model")),
        concurrency=concurrency,
        trials=trials,
        reasoning=reasoning,
    )


def save_state(state: UserState) -> Path:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required; install the project dependencies first") from exc
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(asdict(state), sort_keys=False), encoding="utf-8")
    return path


def update_state(**kwargs: Any) -> UserState:
    """Patch fields of the persisted state and return it."""
    state = load_state()
    for key, value in kwargs.items():
        if not hasattr(state, key):
            raise SystemExit(f"unknown state field: {key}")
        setattr(state, key, value)
    save_state(state)
    return state
