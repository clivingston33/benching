"""Small pure helpers shared by benchmark clients."""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

_REDACTION_PATTERNS = (
    re.compile(r"(authorization\s*:\s*(?:bearer\s+)?)[^\s,;\"]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[:=]\s*)[^\s,;\"]+", re.IGNORECASE),
    re.compile(r"(x-api-key\s*[:=]\s*)[^\s,;\"]+", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*)[^\s,;\"]+", re.IGNORECASE),
)


def utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def redact(value: str | None, limit: int | None = None) -> str | None:
    if value is None:
        return None
    for pattern in _REDACTION_PATTERNS:
        value = pattern.sub(r"\1[REDACTED]", value)
    return value[:limit] if limit is not None else value


def has_stream_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"content", "text", "reasoning_content", "reasoning", "thinking"} and isinstance(item, str) and item:
                return True
            if isinstance(item, (dict, list)) and has_stream_content(item):
                return True
    elif isinstance(value, list):
        return any(has_stream_content(item) for item in value)
    return False


def sse_events(body: bytes) -> Iterator[dict[str, Any]]:
    for line in body.decode("utf-8", "replace").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def stream_summary(body: bytes) -> tuple[bool, str | None, dict[str, Any] | None]:
    first_content = False
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    for event in sse_events(body):
        first_content = first_content or has_stream_content(event)
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        for choice in event.get("choices", []) if isinstance(event.get("choices"), list) else []:
            if isinstance(choice, dict) and choice.get("finish_reason") is not None:
                finish_reason = str(choice["finish_reason"])
    return first_content, finish_reason, usage
