"""Direct staged concurrent-stream capability probe; not a benchmark score."""
from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROMPT = "Reply with a short numbered list of 120 simple words."
MAX_TOKENS = 256


def utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def has_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"content", "text", "reasoning", "reasoning_content", "thinking"} and isinstance(item, str) and item:
                return True
            if isinstance(item, (dict, list)) and has_content(item):
                return True
    elif isinstance(value, list):
        return any(has_content(item) for item in value)
    return False


def parse_stream(body: bytes) -> tuple[bool, str | None, dict[str, Any] | None]:
    first_content = False
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
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
        if not isinstance(event, dict):
            continue
        first_content = first_content or has_content(event)
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        for choice in event.get("choices", []) if isinstance(event.get("choices"), list) else []:
            if isinstance(choice, dict) and choice.get("finish_reason") is not None:
                finish_reason = str(choice["finish_reason"])
    return first_content, finish_reason, usage


def one_request(provider: str, plan: str | None, tier: str, endpoint: str, api_model: str, key: str, requested: int, index: int, barrier: threading.Barrier) -> dict[str, Any]:
    probe_id = uuid.uuid4().hex
    started_mono = time.monotonic()
    started_at = utc()
    result: dict[str, Any] = {
        "schema_version": 1,
        "probe_id": probe_id,
        "provider": provider,
        "configured_plan": plan,
        "configured_plan_tier": tier,
        "requested_concurrency": requested,
        "request_index": index,
        "request_started": started_at,
        "first_content": None,
        "stream_completed": False,
        "http_status": None,
        "retry_after": None,
        "provider_request_id": None,
        "ttft_ms": None,
        "e2e_latency_ms": None,
        "stream_success": False,
        "provider_failure": False,
        "rate_limited": False,
        "finish_reason": None,
        "usage": None,
        "error_type": None,
        "error_message": None,
    }
    try:
        barrier.wait(timeout=10)
        payload = json.dumps({"model": api_model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": MAX_TOKENS, "stream": True, "reasoning": {"enabled": False}}).encode()
        request = Request(endpoint.rstrip("/") + "/chat/completions", data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "provider-benchmark-concurrency-probe/1.0"})
        with urlopen(request, timeout=120) as response:
            result["http_status"] = response.status
            result["retry_after"] = response.headers.get("retry-after")
            result["provider_request_id"] = response.headers.get("x-request-id") or response.headers.get("request-id")
            chunks: list[bytes] = []
            line_buffer = ""
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                line_buffer += chunk.decode("utf-8", "replace")
                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    first_line, _, _ = parse_stream((line + "\n").encode())
                    if first_line and result["first_content"] is None:
                        result["first_content"] = True
                        result["ttft_ms"] = round((time.monotonic() - started_mono) * 1000, 3)
            body = b"".join(chunks)
            first, finish_reason, usage = parse_stream(body)
            result["first_content"] = bool(result["first_content"] or first)
            result["finish_reason"] = finish_reason
            result["usage"] = usage
            result["stream_completed"] = True
            result["e2e_latency_ms"] = round((time.monotonic() - started_mono) * 1000, 3)
            result["stream_success"] = response.status == 200 and bool(result["first_content"])
            result["provider_failure"] = not result["stream_success"]
    except HTTPError as error:
        result["http_status"] = error.code
        result["retry_after"] = error.headers.get("retry-after")
        result["provider_request_id"] = error.headers.get("x-request-id") or error.headers.get("request-id")
        result["rate_limited"] = error.code == 429
        result["provider_failure"] = True
        result["error_type"] = "rate_limited" if error.code == 429 else "http_error"
        result["error_message"] = error.read().decode("utf-8", "replace")[:1000]
    except (URLError, TimeoutError, OSError, threading.BrokenBarrierError) as error:
        result["provider_failure"] = True
        result["error_type"] = type(getattr(error, "reason", error)).__name__
        result["error_message"] = str(error)[:1000]
    except Exception as error:
        result["provider_failure"] = True
        result["error_type"] = type(error).__name__
        result["error_message"] = str(error)[:1000]
    return result


def simultaneous(provider: str, plan: str | None, tier: str, endpoint: str, api_model: str, key: str, requested: int) -> dict[str, Any]:
    barrier = threading.Barrier(requested)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=requested, thread_name_prefix="probe") as pool:
        futures = [pool.submit(one_request, provider, plan, tier, endpoint, api_model, key, requested, index, barrier) for index in range(requested)]
        requests = [future.result() for future in futures]
    intervals = []
    for result in requests:
        if result["e2e_latency_ms"] is not None:
            intervals.append((started, started + float(result["e2e_latency_ms"]) / 1000))
    maximum_observed = 0
    for point in sorted({point for interval in intervals for point in interval}):
        maximum_observed = max(maximum_observed, sum(start <= point <= end for start, end in intervals))
    return {
        "requested_concurrency": requested,
        "successful_simultaneous_streams": sum(1 for result in requests if result["stream_success"]),
        "rejected_simultaneous_streams": sum(1 for result in requests if not result["stream_success"]),
        "maximum_simultaneous_requests_observed": maximum_observed,
        "all_streams_successful": all(result["stream_success"] for result in requests),
        "requests": requests,
    }


def run_probe(provider: str, config: dict[str, Any], endpoint: str, api_model: str, key: str, output_dir: Path) -> tuple[Path, Path]:
    plan = config.get("plan")
    tier = str(config.get("plan_tier", "unknown"))
    tested: list[dict[str, Any]] = []
    for requested in (2, 3, 5, 6):
        stage = simultaneous(provider, plan, tier, endpoint, api_model, key, requested)
        tested.append(stage)
        if requested == 2 and not stage["all_streams_successful"]:
            break
        if requested == 3 and not stage["all_streams_successful"]:
            break
        if requested == 5 and not stage["all_streams_successful"]:
            break
    successful_stages = [stage["requested_concurrency"] for stage in tested if stage["all_streams_successful"]]
    rejected_stages = [stage for stage in tested if not stage["all_streams_successful"]]
    summary = {
        "schema_version": 1,
        "probe_id": uuid.uuid4().hex,
        "created_at_utc": utc(),
        "provider": provider,
        "configured_plan": plan,
        "configured_plan_tier": tier,
        "endpoint": endpoint,
        "api_model": api_model,
        "tested_concurrency": [stage["requested_concurrency"] for stage in tested],
        "highest_verified_concurrency": max(successful_stages) if successful_stages else 0,
        "first_rejected_concurrency": rejected_stages[0]["requested_concurrency"] if rejected_stages else None,
        "rejection_status": next((request.get("http_status") for stage in rejected_stages for request in stage["requests"] if not request.get("stream_success") and request.get("http_status") is not None), None),
        "limit_verified": bool(rejected_stages),
        "stages": tested,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"concurrency-probe-{provider}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    summary_path = output_dir / f"{stem}.json"
    jsonl_path = output_dir / f"{stem}.jsonl"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    jsonl_path.write_text("".join(json.dumps(request, separators=(",", ":")) + "\n" for stage in tested for request in stage["requests"]), encoding="utf-8")
    return summary_path, jsonl_path
