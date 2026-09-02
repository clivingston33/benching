"""Provider preflight validation against a live OpenAI-compatible API."""
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from benchmark._paths import RUNS
from benchmark._util import redact, stream_summary, utc
from benchmark.config import BenchmarkSpec, provider_config, resolve


def sanitized(text: str, limit: int = 4096) -> str:
    return redact(text, limit) or ""


def provider_request_id(headers: Any) -> str | None:
    return headers.get("x-request-id") or headers.get("request-id")


def parse_stream_body(body: bytes) -> tuple[bool, dict[str, Any] | None]:
    first_content, _, usage = stream_summary(body)
    return first_content, usage


def validation_request(url: str, key: str, api_model: str) -> dict[str, Any]:
    """Send a minimal streaming chat completion and record what happens."""
    payload = json.dumps({"model": api_model, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 4, "stream": True}).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "benching/1.0"}
    started = time.monotonic()
    result: dict[str, Any] = {"url": url, "api_model": api_model, "stream": True, "user_agent": "benching/1.0", "streaming": False, "first_content": False, "usage": None}
    try:
        with urlopen(Request(url, data=payload, headers=headers), timeout=90) as response:
            body = response.read()
            result.update(status=response.status, duration_ms=round((time.monotonic() - started) * 1000, 3), bytes=len(body), content_type=response.headers.get("content-type"), provider_request_id=provider_request_id(response.headers), server=response.headers.get("server"), cf_ray=response.headers.get("cf-ray"), via=response.headers.get("via"), http_version="unknown")
            result["streaming"] = "text/event-stream" in (response.headers.get("content-type", "").lower())
            result["first_content"], result["usage"] = parse_stream_body(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        result.update(status=error.code, duration_ms=round((time.monotonic() - started) * 1000, 3), provider_request_id=provider_request_id(error.headers), server=error.headers.get("server"), cf_ray=error.headers.get("cf-ray"), via=error.headers.get("via"), http_version="unknown", error_body=sanitized(body))
    except (URLError, TimeoutError, OSError) as error:
        result.update(status=None, duration_ms=round((time.monotonic() - started) * 1000, 3), error_type=type(getattr(error, "reason", error)).__name__, error_body=sanitized(str(error)))
    return result


def classify_validation(result: dict[str, Any]) -> str:
    """Categorize a validation result into a stable error class."""
    status = result.get("status")
    if status in {401, 403}:
        if result.get("cf_ray") or str(result.get("server", "")).lower() == "cloudflare":
            return "edge_access_denied"
        return "authentication_failure"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if status is None:
        return "network_failure"
    if isinstance(status, int) and status >= 500:
        return "provider_internal_error"
    return "provider_response"


def validate_provider(
    name: str,
    spec: BenchmarkSpec,
    root_config: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    env_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate a provider's credentials and model availability.

    Returns the full validation result dict. Raises ``SystemExit`` when the
    provider cannot be used (missing credential, missing model, or a failed
    streaming completion). No result file is written here; callers decide.
    """
    from benchmark.config import env_path, provider_env_values

    if config is None:
        root_config, config = provider_config(name, root_config)
    assert root_config is not None
    env_values = env_values if env_values is not None else provider_env_values(name, config)
    endpoint, api_model = resolve(name, config, env_values)
    key = env_values.get(str(config["auth_env"]))
    if not key:
        raise SystemExit(f"missing credential: {config['auth_env']}")
    result: dict[str, Any] = {"schema_version": 1, "provider": name, "provider_plan": config.get("plan"), "benchmark_model": spec.model, "api_model": api_model, "base_url": endpoint, "models": None}
    if config.get("strict_model_check"):
        try:
            with urlopen(Request(endpoint + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30) as response:
                catalog = json.loads(response.read())
                ids = [item.get("id") for item in catalog.get("data", []) if isinstance(item, dict) and item.get("id")] if isinstance(catalog, dict) else []
                result["models"] = {"status": response.status, "count": len(ids), "api_model_present": api_model in ids}
                if api_model not in ids:
                    raise SystemExit(f"{name} api_model not present in /models: {api_model}")
        except HTTPError as error:
            result["models"] = {"status": error.code, "error_body": sanitized(error.read().decode("utf-8", "replace"))}
            raise SystemExit(json.dumps(result, indent=2))
    else:
        try:
            with urlopen(Request(endpoint + "/models", headers={"Authorization": f"Bearer {key}"}), timeout=30) as response:
                catalog = json.loads(response.read())
                result["models"] = {"status": response.status, "catalog_count": len(catalog.get("data", [])) if isinstance(catalog, dict) and isinstance(catalog.get("data"), list) else None}
        except HTTPError as error:
            result["models"] = {"status": error.code, "error_body": sanitized(error.read().decode("utf-8", "replace")), "server": error.headers.get("server"), "cf_ray": error.headers.get("cf-ray")}
        except Exception as error:
            result["models"] = {"status": None, "error_body": sanitized(str(error))}
    result["chat_completions"] = validation_request(endpoint + "/chat/completions", key, api_model)
    result["error_class"] = classify_validation(result["chat_completions"])
    result["models_error_class"] = classify_validation(result["models"]) if isinstance(result.get("models"), dict) and result["models"].get("status") is not None else None
    result["success"] = result["chat_completions"].get("status") == 200 and result["chat_completions"].get("streaming") and result["chat_completions"].get("first_content")
    return result


def write_validation_report(name: str, result: dict[str, Any]) -> Path:
    """Persist a validation result under runs/ as validation-<name>-*.json."""
    output = RUNS / f"validation-{name}-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    return output
