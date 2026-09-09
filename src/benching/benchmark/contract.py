"""Canonical artifact contract checks (M2 task 7).

Authoritative schemas ship inside this package under
``benchmark/schemas/`` (single producer source; the dashboard mirrors
them via its sync check). This module loads them through package
resource APIs so validation works identically from a source checkout
and from a wheel installed outside the repository, and validates
producer output plus semantic invariants that JSON Schema alone cannot
express. Consumers in other languages implement the same checks against
the same schema files.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from benching.benchmark._paths import resource_text

SUMMARY_SCHEMA = "summary-v1.schema.json"
COMPARISON_SCHEMA = "comparison-v1.schema.json"


def load_schema(name: str) -> dict[str, Any]:
    """Load one authoritative schema document by filename."""
    try:
        value = json.loads(resource_text("schemas", name))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"unreadable contract schema: {name} ({type(exc).__name__})") from None
    if not isinstance(value, dict):
        raise SystemExit(f"invalid contract schema: {name} (expected object)")
    return value


@lru_cache(maxsize=4)
def _validator(schema_name: str):
    try:
        import jsonschema
    except ImportError as exc:
        raise SystemExit("jsonschema is required; install the project dependencies first") from exc
    return jsonschema.Draft202012Validator(load_schema(schema_name))


def _format_errors(errors: Any) -> list[str]:
    messages = []
    for error in sorted(errors, key=lambda item: (list(item.absolute_path), item.message)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{location}: {error.message[:200]}")
    return messages


def validate_summary(summary: Any) -> list[str]:
    """Schema errors for a summary document (empty when valid)."""
    return _format_errors(_validator(SUMMARY_SCHEMA).iter_errors(summary))


def validate_comparison(comparison: Any) -> list[str]:
    """Schema errors for a comparison document (empty when valid)."""
    return _format_errors(_validator(COMPARISON_SCHEMA).iter_errors(comparison))


def check_comparison_consistency(comparison: dict[str, Any]) -> list[str]:
    """Identity checks JSON Schema cannot express; empty when consistent.

    Only compares run id lists. Embedded summaries are validated
    separately with validate_summary by every consumer.
    """
    problems: list[str] = []
    runs = comparison.get("runs")
    if not isinstance(runs, list) or not runs:
        return ["comparison has no embedded runs"]
    embedded = [run.get("run_id") if isinstance(run, dict) else None for run in runs]
    if embedded != list(comparison.get("run_ids") or []):
        problems.append("comparison run_ids do not match embedded summary run ids")
    return problems


def check_summary_invariants(summary: dict[str, Any]) -> list[str]:
    """Producer invariants beyond shape; empty when consistent."""
    problems: list[str] = []

    def _rate(value: Any) -> bool:
        return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1)

    reliability = summary.get("reliability") if isinstance(summary.get("reliability"), dict) else {}
    for key in ("success_rate", "request_success_rate", "stream_completion_rate", "http_error_rate", "timeout_rate"):
        if not _rate(reliability.get(key)):
            problems.append(f"reliability.{key} out of range: {reliability.get(key)!r}")
    for task in summary.get("tasks", []) if isinstance(summary.get("tasks"), list) else []:
        if not isinstance(task, dict):
            problems.append("task entry is not an object")
            continue
        # Null pass is legitimate for timeouts/exceptions with missing
        # reward and for explicit missing-work markers; a set reward with
        # null pass, or any pass/fail claim with zero requests, is not.
        if task.get("passed") is None and task.get("reward") is not None:
            problems.append(f"task {task.get('task_id')}: null pass with reward set")
        if task.get("requests") == 0 and (task.get("passed") is not None):
            problems.append(f"task {task.get('task_id')}: zero requests but a verifier pass/fail claim")
    context = summary.get("context") if isinstance(summary.get("context"), dict) else {}
    if "unknown" in context:
        bucketed = sum(
            bucket.get("requests", 0)
            for bucket in context.values()
            if isinstance(bucket, dict) and isinstance(bucket.get("requests"), int)
        )
        analyzed = (reliability.get("successful_requests") or 0) + (reliability.get("failed_requests") or 0)
        if bucketed != analyzed:
            problems.append(f"context buckets account {bucketed} requests but {analyzed} were analyzed")
    return problems

