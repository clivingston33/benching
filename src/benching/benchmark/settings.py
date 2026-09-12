"""Effective execution settings shared by Typer commands and the slash shell.

One definition of precedence for every execution surface:

explicit command override
→ persisted user default (:mod:`benching.benchmark.state`)
→ packaged default (the active benchmark manifest)

``benching run`` and ``/run`` resolve the same effective provider, model,
reasoning, concurrency, and trials through :func:`effective_settings`;
tokenizer status/prepare and the runner resolve the same tokenizer identity
through :func:`tokenizer_context` in :mod:`benching.benchmark.tokenizer`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from benching.benchmark.benchmarks import active_root_config
from benching.benchmark.config import BenchmarkSpec, benchmark_spec, enabled_providers
from benching.benchmark.state import load_state


@dataclass(frozen=True)
class EffectiveSettings:
    """Resolved execution settings plus the config they were resolved from."""

    provider: str | None
    model: str | None
    reasoning: str
    concurrency: int
    trials: int
    root: dict[str, Any]
    spec: BenchmarkSpec


def effective_settings(
    provider: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    concurrency: int | None = None,
    trials: int | None = None,
) -> EffectiveSettings:
    """Resolve one effective configuration for every execution surface.

    Each explicit argument wins; otherwise the persisted user default
    applies. A ``None`` model means "provider default" and is resolved to
    a concrete model later by :func:`benching.benchmark.config.resolve`.
    """
    state = load_state()
    root = active_root_config()
    return EffectiveSettings(
        provider=provider if provider is not None else state.active_provider,
        model=model if model is not None else state.model,
        reasoning=reasoning if reasoning is not None else state.reasoning,
        concurrency=concurrency if concurrency is not None else state.concurrency,
        trials=trials if trials is not None else state.trials,
        root=root,
        spec=benchmark_spec(root),
    )


def run_options(
    mode: str,
    provider: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    concurrency: int | None = None,
    trials: int | None = None,
) -> tuple:
    """Build runner :class:`RunOptions` from one effective configuration.

    Returns ``(options, settings)`` so callers share the resolved spec and
    root without resolving twice. Raises ``SystemExit`` (no provider /
    not enabled) with the same messages every caller translates into its
    own surface error.
    """
    from benching.benchmark.runner import RunOptions

    settings = effective_settings(
        provider=provider, model=model, reasoning=reasoning,
        concurrency=concurrency, trials=trials,
    )
    if not settings.provider:
        raise SystemExit("no provider given and no active provider; run `benching provider use NAME` or pass PROVIDER")
    configured = set(enabled_providers(settings.root))
    if settings.provider not in configured:
        raise SystemExit(f"provider is not enabled: {settings.provider} (enabled: {', '.join(sorted(configured)) or 'none'})")
    return (
        RunOptions(
            provider=settings.provider,
            mode=mode,
            benchmark_model=settings.model,
            reasoning=settings.reasoning,
            concurrency=settings.concurrency,
            trials=settings.trials,
        ),
        settings,
    )
