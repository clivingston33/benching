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

from benching.benchmark._paths import runs_root
from benching.benchmark._util import stream_summary, utc
from benching.benchmark.config import BenchmarkSpec, provider_config, provider_env_values, resolve
from benching.benchmark.validation import validate_provider

PROMPT = "Reply with a short numbered list of 120 simple words."
MAX_TOKENS = 256


def parse_stream(body: bytes) -> tuple[bool, str | None, dict[str, Any] | None]:
    return stream_summary(body)


def one_request(provider: str, plan: str | None, tier: str, endpoint: str, api_model: str, key: str, requested: int, index: int, barrier: threading.Barrier) -> dict[str, Any]:
    from benching.benchmark._util import redact as _redact
    from benching.benchmark.security import validate_api_key, validate_endpoint, validate_model_name

    probe_id = uuid.uuid4().hex
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
        # Shared boundary: never transmit Authorization to an unsafe endpoint.
        normalized_endpoint = validate_endpoint(endpoint)
        validate_api_key(key)
        validate_model_name(api_model)
    except SystemExit as exc:
        result["provider_failure"] = True
        result["error_type"] = "invalid_endpoint"
        result["error_message"] = (_redact(str(exc.code or exc)) or "")[:1000]
        return result
    try:
        barrier.wait(timeout=10)
        # Real execution interval starts at barrier release: TTFT, end to
        # end latency, and overlap are measured from here, never including
        # barrier wait time.
        exec_start_mono = time.monotonic()
        result["exec_start_mono"] = exec_start_mono
        payload = json.dumps({"model": api_model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": MAX_TOKENS, "stream": True, "reasoning": {"enabled": False}}).encode()
        request = Request(normalized_endpoint + "/chat/completions", data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "benching-concurrency-probe/1.0"})
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
                        result["ttft_ms"] = round((time.monotonic() - exec_start_mono) * 1000, 3)
            body = b"".join(chunks)
            first, finish_reason, usage = parse_stream(body)
            result["first_content"] = bool(result["first_content"] or first)
            result["finish_reason"] = finish_reason
            result["usage"] = usage
            result["stream_completed"] = True
            result["e2e_latency_ms"] = round((time.monotonic() - exec_start_mono) * 1000, 3)
            result["stream_success"] = response.status == 200 and bool(result["first_content"])
            result["provider_failure"] = not result["stream_success"]
    except HTTPError as error:
        from benching.benchmark._util import redact as _redact2

        result["http_status"] = error.code
        result["retry_after"] = error.headers.get("retry-after")
        result["provider_request_id"] = error.headers.get("x-request-id") or error.headers.get("request-id")
        result["rate_limited"] = error.code == 429
        result["provider_failure"] = True
        result["error_type"] = "rate_limited" if error.code == 429 else "http_error"
        result["error_message"] = (_redact2(error.read().decode("utf-8", "replace")) or "")[:1000]
    except (URLError, TimeoutError, OSError, threading.BrokenBarrierError) as error:
        from benching.benchmark._util import redact as _redact3

        result["provider_failure"] = True
        result["error_type"] = type(getattr(error, "reason", error)).__name__
        result["error_message"] = (_redact3(str(error)) or "")[:1000]
    except Exception as error:
        from benching.benchmark._util import redact as _redact4

        result["provider_failure"] = True
        result["error_type"] = type(error).__name__
        result["error_message"] = (_redact4(str(error)) or "")[:1000]
    finally:
        # Every outcome carries a real execution interval; requests that
        # never passed the barrier simply lack a start.
        result.setdefault("exec_end_mono", time.monotonic())
    return result


def _execution_interval(result: dict[str, Any]) -> tuple[float, float] | None:
    """Real post-barrier execution interval, or None when never executed."""
    start = result.get("exec_start_mono")
    end = result.get("exec_end_mono")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return None
    if end < start:
        return None
    return (float(start), float(end))


def _max_overlap(intervals: list[tuple[float, float]]) -> int:
    """Maximum requests simultaneously in flight over real intervals."""
    maximum_observed = 0
    for point in sorted({point for interval in intervals for point in interval}):
        maximum_observed = max(maximum_observed, sum(start <= point <= end for start, end in intervals))
    return maximum_observed


def simultaneous(provider: str, plan: str | None, tier: str, endpoint: str, api_model: str, key: str, requested: int) -> dict[str, Any]:
    """Measure staged concurrent streams and their real client-side overlap.

    Overlap is computed from actual per-request post-barrier execution
    intervals. It describes what this client observed overlapping locally,
    not provider capacity: a low number may reflect client scheduling
    rather than a provider limit.
    """
    barrier = threading.Barrier(requested)
    with ThreadPoolExecutor(max_workers=requested, thread_name_prefix="probe") as pool:
        futures = [pool.submit(one_request, provider, plan, tier, endpoint, api_model, key, requested, index, barrier) for index in range(requested)]
        requests = [future.result() for future in futures]
    intervals = [interval for interval in (_execution_interval(result) for result in requests) if interval is not None]
    maximum_observed = _max_overlap(intervals)
    return {
        "requested_concurrency": requested,
        "successful_simultaneous_streams": sum(1 for result in requests if result["stream_success"]),
        "rejected_simultaneous_streams": sum(1 for result in requests if not result["stream_success"]),
        "maximum_simultaneous_requests_observed": maximum_observed,
        "all_streams_successful": all(result["stream_success"] for result in requests),
        "requests": requests,
    }


def run_probe(provider: str, config: dict[str, Any], endpoint: str, api_model: str, key: str, output_dir: Path, stages: tuple[int, ...] = (2, 3, 5, 6)) -> tuple[Path, Path]:
    plan = config.get("plan")
    tier = str(config.get("plan_tier", "unknown"))
    tested: list[dict[str, Any]] = []
    for index, requested in enumerate(stages):
        stage = simultaneous(provider, plan, tier, endpoint, api_model, key, requested)
        tested.append(stage)
        if not stage["all_streams_successful"] and index < len(stages) - 1:
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
    from benching.benchmark.io import dump_json_atomic, write_text_atomic

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"concurrency-probe-{provider}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    summary_path = output_dir / f"{stem}.json"
    jsonl_path = output_dir / f"{stem}.jsonl"
    dump_json_atomic(summary_path, summary)
    write_text_atomic(jsonl_path, "".join(json.dumps(request, separators=(",", ":")) + "\n" for stage in tested for request in stage["requests"]))
    return summary_path, jsonl_path


def probe_provider(
    name: str,
    spec: BenchmarkSpec,
    root_config: dict[str, Any] | None = None,
    stages: tuple[int, ...] = (2, 3, 5, 6),
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Validate a provider then stage concurrent streams against it."""
    from benching.benchmark.security import validate_api_key, validate_registry_name

    output_dir = output_dir if output_dir is not None else runs_root()
    validate_registry_name(name, "provider")
    root_config, config = provider_config(name, root_config)
    values = provider_env_values(name, config)
    # resolve() enforces the shared HTTPS boundary before any network.
    endpoint, api_model = resolve(name, config, values)
    result = validate_provider(name, spec, root_config, config, values)
    if not result["success"]:
        raise SystemExit(f"provider validation failed: {result['error_class']}")
    key = values.get(str(config["auth_env"]))
    if not key:
        raise SystemExit(f"missing credential: {config['auth_env']}")
    validate_api_key(key)
    return run_probe(name, config, endpoint, api_model, key, output_dir, stages)

