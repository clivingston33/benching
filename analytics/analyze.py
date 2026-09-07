#!/usr/bin/env python3
"""Normalize run telemetry and compare compatible benchmark runs."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tokenizers import Tokenizer

from benchmark.status import scan_harbor_result_list

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = ((0, 4096, "0-4K"), (4096, 16384, "4K-16K"), (16384, 32768, "16K-32K"), (32768, 65536, "32K-64K"), (65536, math.inf, "64K+"))


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except json.JSONDecodeError:
            continue
    return rows


def metric(value: Any, source: str) -> dict[str, Any]:
    return {"value": value, "source": source if value is not None else "unavailable"}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return round(ordered[low], 6)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 6)


def distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "p5": None, "p25": None, "p75": None, "p90": None, "p95": None, "p99": None, "stdev": None, "cv": None}
    mean = statistics.fmean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "count": len(values),
        "mean": round(mean, 6),
        "median": round(statistics.median(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "p5": percentile(values, 0.05),
        "p25": percentile(values, 0.25),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "stdev": round(stdev, 6),
        "cv": round(stdev / mean, 6) if mean else None,
    }


def local_tokenizer(path: str | None) -> Tokenizer | None:
    if not path:
        return None
    tokenizer_path = Path(path)
    if tokenizer_path.is_dir():
        tokenizer_path /= "tokenizer.json"
    if not tokenizer_path.is_file():
        return None
    try:
        return Tokenizer.from_file(str(tokenizer_path))
    except Exception:
        return None


def local_count(tokenizer: Any, text: str, truncated: bool) -> int | None:
    if tokenizer is None or truncated:
        return None
    try:
        encoded = tokenizer.encode(text, add_special_tokens=False)
        return len(encoded.ids) if hasattr(encoded, "ids") else len(encoded)
    except Exception:
        return None


def normalize(run: dict[str, Any], raw: list[dict[str, Any]], tokenizer: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in raw:
        if row.get("event_type") != "inference":
            continue
        timing = row.get("timing") if isinstance(row.get("timing"), dict) else {}
        tokens = row.get("tokens") if isinstance(row.get("tokens"), dict) else {}
        first = timing.get("first_content_output_ms")
        last = timing.get("last_content_output_ms")
        end = timing.get("stream_completed_ms")
        decode_ms = round(float(last) - float(first), 6) if first is not None and last is not None and float(last) >= float(first) else None
        output_text = str(row.get("output_text") or "")
        output_local = local_count(tokenizer, output_text, bool(row.get("output_text_truncated")))
        decode_tps = round(output_local / (decode_ms / 1000), 6) if output_local is not None and decode_ms and decode_ms > 0 else None
        effective_tps = round(output_local / (float(end) / 1000), 6) if output_local is not None and end and float(end) > 0 else None
        provider_tokens = {
            key: metric(tokens.get(key), "reported" if tokens.get(key) is not None else "unavailable")
            for key in ("input_provider", "output_provider", "total_provider", "cache_read", "cache_write")
        }
        downstream_cancelled = bool(row.get("downstream_cancelled")) or row.get("error_type") == "downstream_disconnect"
        provider_failure = bool(row.get("provider_failure"))
        normalized = {
            "schema_version": 1,
            "run_id": row.get("run_id") or run.get("run_id"),
            "request_id": row.get("request_id"),
            "task_id": row.get("task_id") or "unknown",
            "trial_id": row.get("trial_id") or "unknown",
            "agent_invocation_id": row.get("agent_invocation_id"),
            "provider": row.get("provider") or run.get("provider"),
            "provider_plan": row.get("provider_plan") or run.get("provider_plan"),
            "provider_plan_tier": row.get("provider_plan_tier") or run.get("provider_plan_tier", "unknown"),
            "provider_request_id": row.get("provider_request_id"),
            "benchmark_model": row.get("benchmark_model") or run.get("benchmark_model"),
            "api_model": row.get("model") or run.get("api_model"),
            "timing": {
                "ttft_ms": metric(first, "measured"),
                "decode_duration_ms": metric(decode_ms, "measured"),
                "end_to_end_latency_ms": metric(end, "measured"),
                "decode_tps": metric(decode_tps, "calculated"),
                "effective_tps": metric(effective_tps, "calculated"),
            },
            "tokens": {
                **provider_tokens,
                "output_local": metric(output_local, "calculated"),
            },
            "reliability": {
                "success": bool(row.get("success")),
                "stream_completed": bool(row.get("stream_completed")),
                "downstream_cancelled": downstream_cancelled,
                "provider_failure": provider_failure,
                "provider_stream_failure": provider_failure and not downstream_cancelled,
                "incomplete_provider_stream": not bool(row.get("stream_completed")) and not downstream_cancelled,
                "http_status": row.get("http_status"),
                "finish_reason": row.get("finish_reason"),
                "timeout": row.get("error_type") in {"TimeoutError", "asyncio.TimeoutError"} or row.get("http_status") in {408, 504},
                "error_type": row.get("error_type"),
                "error_message": row.get("error_message"),
                "retry_index": 0,
            },
            "routing": row.get("routing") or {"backend": None, "region": None},
            "output_text_complete": not bool(row.get("output_text_truncated")),
        }
        output.append(normalized)
    return output


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def values(rows: list[dict[str, Any]], section: str, key: str) -> list[float]:
    result: list[float] = []
    for row in rows:
        value = ((row.get(section) or {}).get(key) or {}).get("value")
        if isinstance(value, (int, float)):
            result.append(float(value))
    return result

def harbor_task_results(run_dir: Path) -> list[dict[str, Any]]:
    return scan_harbor_result_list(run_dir / "harbor")


def _benchmark_from_task_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(result.get("passed") is True for result in results)
    timed_out = sum(result.get("timeout") is True for result in results)
    errored = sum(bool(result.get("exception_type")) and not result.get("timeout") for result in results)
    return {
        "total_tasks": total,
        "completed_tasks": max(0, total - timed_out - errored),
        "passed_tasks": passed,
        "failed_tasks": max(0, total - passed - timed_out - errored),
        "errored_tasks": errored,
        "timeout_tasks": timed_out,
        "model_calls": None,
        "score": passed / total if total else None,
        "retries": None,
    }


def benchmark_result(run_dir: Path) -> dict[str, Any]:
    results = harbor_task_results(run_dir)
    aggregate = next(iter(sorted((run_dir / "harbor").glob("*/result.json"))), None)
    if aggregate is None:
        return _benchmark_from_task_results(results)
    try:
        result = read_json(aggregate)
    except (OSError, ValueError):
        return _benchmark_from_task_results(results)
    stats = result.get("stats") if isinstance(result.get("stats"), dict) else {}
    evaluations = stats.get("evals") if isinstance(stats.get("evals"), dict) else {}
    evaluation = next(iter(evaluations.values()), {}) if evaluations else {}
    rewards = ((evaluation.get("reward_stats") or {}).get("reward") or {}) if isinstance(evaluation, dict) else {}
    passed = len(rewards.get("1.0", [])) if isinstance(rewards, dict) else 0
    errors = stats.get("n_errored_trials", 0)
    total = result.get("n_total_trials", 0)
    completed = stats.get("n_completed_trials", 0)
    exceptions = evaluation.get("exception_stats", {}) if isinstance(evaluation, dict) else {}
    timeout_tasks = len(exceptions.get("VerifierTimeoutError", [])) if isinstance(exceptions, dict) else 0
    if not total and results:
        return _benchmark_from_task_results(results)
    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "passed_tasks": passed,
        "failed_tasks": max(0, completed - passed - errors),
        "errored_tasks": errors,
        "timeout_tasks": timeout_tasks,
        "model_calls": None,
        "score": passed / total if total else None,
        "retries": stats.get("n_retries"),
    }


def summarize(run: dict[str, Any], rows: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    success = sum(1 for row in rows if row["reliability"]["success"])
    streams = sum(1 for row in rows if row["reliability"]["stream_completed"])
    errors = len(rows) - success
    downstream_cancelled = sum(1 for row in rows if row["reliability"]["downstream_cancelled"])
    provider_failures = sum(1 for row in rows if row["reliability"]["provider_stream_failure"])
    incomplete_provider_streams = sum(1 for row in rows if row["reliability"]["incomplete_provider_stream"])
    return {
        "provider": run.get("provider"),
        "provider_plan": run.get("provider_plan"),
        "provider_plan_tier": run.get("provider_plan_tier", "unknown"),
        "benchmark_model": run.get("benchmark_model"),
        "api_model": run.get("api_model"),
        "requests": len(rows),
        "reliability": {
            "request_success_rate": success / len(rows) if rows else None,
            "stream_completion_rate": streams / len(rows) if rows else None,
            "http_error_rate": sum(1 for row in rows if isinstance(row["reliability"].get("http_status"), int) and row["reliability"]["http_status"] >= 400) / len(rows) if rows else None,
            "timeout_rate": sum(1 for row in rows if row["reliability"]["timeout"]) / len(rows) if rows else None,
            "provider_failures": provider_failures,
            "downstream_cancellations": downstream_cancelled,
            "incomplete_provider_streams": incomplete_provider_streams,
            "errors": errors,
        },
        "timing": {
            "ttft_ms": distribution(values(rows, "timing", "ttft_ms")),
            "decode_duration_ms": distribution(values(rows, "timing", "decode_duration_ms")),
            "end_to_end_latency_ms": distribution(values(rows, "timing", "end_to_end_latency_ms")),
            "decode_tps": distribution(values(rows, "timing", "decode_tps")),
            "effective_tps": distribution(values(rows, "timing", "effective_tps")),
        },
        "tokens": {
            "input_provider": sum(values(rows, "tokens", "input_provider")) or None,
            "output_provider": sum(values(rows, "tokens", "output_provider")) or None,
            "output_local": sum(values(rows, "tokens", "output_local")) or None,
        },
        "benchmark": benchmark_result(run_dir),
        "context_buckets": context_buckets(rows),
    }
def _summary_distribution(rows: list[dict[str, Any]], section: str, key: str) -> dict[str, Any]:
    result = distribution(values(rows, section, key))
    result["p50"] = result["median"]
    return result


def _sum_metric(rows: list[dict[str, Any]], key: str) -> int | float | None:
    values_for_key = values(rows, "tokens", key)
    return sum(values_for_key) if values_for_key else None

def task_summaries(rows: list[dict[str, Any]], run_dir: Path) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("task_id") or "unknown"), str(row.get("trial_id") or "unknown"))
        grouped.setdefault(key, []).append(row)
    results = harbor_task_results(run_dir)
    by_key = {(result["task_id"], result["trial_id"]): result for result in results if result.get("trial_id") is not None}
    without_trial = {result["task_id"]: result for result in results if result.get("trial_id") is None}
    keys = set(grouped)
    for result in results:
        task_id = result["task_id"]
        matching = [key for key in grouped if key[0] == task_id]
        if result.get("trial_id") is None and len(matching) == 1:
            continue
        keys.add((task_id, result.get("trial_id")))

    output = []
    for task_id, trial_id in sorted(keys, key=lambda key: (key[0], str(key[1]))):
        task_rows = grouped.get((task_id, trial_id), [])
        result = by_key.get((task_id, trial_id))
        if result is None and len([key for key in grouped if key[0] == task_id]) == 1:
            result = without_trial.get(task_id)
        successful = sum(row.get("reliability", {}).get("success") is True for row in task_rows)
        request_count = len(task_rows)
        ttft = _summary_distribution(task_rows, "timing", "ttft_ms")
        end_to_end = _summary_distribution(task_rows, "timing", "end_to_end_latency_ms")
        output.append(
            {
                "task_id": task_id,
                "trial_id": trial_id,
                "passed": result.get("passed") if result else None,
                "reward": result.get("reward") if result else None,
                "duration_sec": result.get("duration_sec") if result else None,
                "exception": result.get("exception_type") if result else None,
                "timeout": result.get("timeout") if result else None,
                "requests": request_count,
                "tokens": {
                    "input": _sum_metric(task_rows, "input_provider"),
                    "output": _sum_metric(task_rows, "output_provider"),
                    "cache_read": _sum_metric(task_rows, "cache_read"),
                    "cache_write": _sum_metric(task_rows, "cache_write"),
                },
                "latency": {
                    "ttft_ms_mean": ttft["mean"],
                    "ttft_ms_p50": ttft["p50"],
                    "ttft_ms_p95": ttft["p95"],
                    "end_to_end_latency_ms_mean": end_to_end["mean"],
                },
                "reliability": {
                    "successful_requests": successful,
                    "failed_requests": request_count - successful,
                    "success_rate": successful / request_count if request_count else None,
                },
            }
        )
    return output


def canonical_context(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for name, bucket in context_buckets(rows).items():
        output[name] = {
            "requests": bucket["requests"],
            "ttft_ms": {"mean": bucket["ttft_ms"]["mean"], "p50": bucket["ttft_ms"]["median"], "p95": bucket["ttft_ms"]["p95"]},
            "decode_tps": {"mean": bucket["decode_tps"]["mean"], "p50": bucket["decode_tps"]["median"], "p95": bucket["decode_tps"]["p95"]},
            "end_to_end_latency_ms": {"mean": bucket["end_to_end_latency_ms"]["mean"]},
            "failure_rate": bucket["failure_rate"],
        }
    return output


def build_summary(run: dict[str, Any], rows: list[dict[str, Any]], run_dir: Path) -> dict[str, Any]:
    """Build the self-contained dashboard artifact for one analyzed run."""
    benchmark = benchmark_result(run_dir)
    task_names = run.get("tasks") if isinstance(run.get("tasks"), list) else []
    task_count = run.get("task_count")
    if not isinstance(task_count, int):
        task_count = len(task_names) or benchmark.get("total_tasks") or len({row.get("task_id") for row in rows})
    provider_id = run.get("provider")
    reliability = summarize(run, rows, run_dir)["reliability"]
    successful_requests = sum(1 for row in rows if row.get("reliability", {}).get("success"))
    failed_requests = len(rows) - successful_requests
    reliability.update(
        {
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "success_rate": successful_requests / len(rows) if rows else None,
        }
    )
    score = {
        "value": benchmark.get("score"),
        "passed": benchmark.get("passed_tasks"),
        "failed": benchmark.get("failed_tasks"),
        "total": benchmark.get("total_tasks") or task_count,
        "success_rate": benchmark.get("score"),
        "errored": benchmark.get("errored_tasks"),
        "timeout": benchmark.get("timeout_tasks"),
    }
    speed = {
        "decode_tps": _summary_distribution(rows, "timing", "decode_tps"),
        "effective_tps": _summary_distribution(rows, "timing", "effective_tps"),
    }
    speed.update(
        {
            "output_tps_mean": speed["decode_tps"]["mean"],
            "output_tps_p50": speed["decode_tps"]["p50"],
            "output_tps_p95": speed["decode_tps"]["p95"],
        }
    )
    latency = {
        "ttft_ms": _summary_distribution(rows, "timing", "ttft_ms"),
        "decode_duration_ms": _summary_distribution(rows, "timing", "decode_duration_ms"),
        "end_to_end_latency_ms": _summary_distribution(rows, "timing", "end_to_end_latency_ms"),
    }
    latency.update(
        {
            "ttft_ms_mean": latency["ttft_ms"]["mean"],
            "ttft_ms_p50": latency["ttft_ms"]["p50"],
            "ttft_ms_p95": latency["ttft_ms"]["p95"],
        }
    )
    tokens = {key: _sum_metric(rows, key) for key in ("input_provider", "output_provider", "total_provider", "cache_read", "cache_write", "output_local")}
    tokens.update({"input": tokens["input_provider"], "output": tokens["output_provider"]})
    tasks = task_summaries(rows, run_dir)
    return {
        "schema_version": 1,
        "run_id": run.get("run_id") or run_dir.name,
        "created_at_utc": run.get("created_at_utc") or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "benchmark": {
            "name": run.get("benchmark"),
            "version": run.get("benchmark_version"),
            "task_count": task_count,
        },
        "provider": {
            "id": provider_id,
            "name": run.get("provider_name") or provider_id,
        },
        "model": run.get("model") or run.get("api_model") or run.get("benchmark_model"),
        "reasoning": run.get("reasoning_mode") or (run.get("effective_settings") or {}).get("reasoning"),
        "execution": {
            "concurrency": run.get("concurrency"),
            "trials": run.get("trials"),
        },
        "score": score,
        "speed": speed,
        "latency": latency,
        "reliability": reliability,
        "tokens": tokens,
        "context": canonical_context(rows),
        "tasks": tasks,
    }


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")



def context_buckets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for lower, upper, name in BUCKETS:
        selected = []
        for row in rows:
            value = (row["tokens"]["input_provider"] or {}).get("value")
            if isinstance(value, (int, float)) and lower <= value < upper:
                selected.append(row)
        output[name] = {
            "requests": len(selected),
            "ttft_ms": distribution(values(selected, "timing", "ttft_ms")),
            "decode_tps": distribution(values(selected, "timing", "decode_tps")),
            "end_to_end_latency_ms": distribution(values(selected, "timing", "end_to_end_latency_ms")),
            "failure_rate": sum(1 for row in selected if not row["reliability"]["success"]) / len(selected) if selected else None,
        }
    return output
def tokenizer_identity(run: dict[str, Any]) -> tuple[Any, Any]:
    info = run.get("tokenizer") if isinstance(run.get("tokenizer"), dict) else {}
    return info.get("repo"), info.get("revision")


def tokenizer_path_from_run(run: dict[str, Any]) -> str | None:
    info = run.get("tokenizer") if isinstance(run.get("tokenizer"), dict) else {}
    path = info.get("local_cache")
    return path if isinstance(path, str) and path else None


def compatible(runs: list[dict[str, Any]]) -> None:
    fields = ("benchmark", "benchmark_version", "reasoning_mode", "streaming", "concurrency", "trials", "proxy_schema_version", "tasks")
    for field in fields:
        values_for_field = {json.dumps(run.get(field), sort_keys=True) for run in runs}
        if len(values_for_field) != 1:
            raise SystemExit(f"incompatible runs: {field}")

def normalize_runs(run_paths: list[Path], execution: str = "sequential", write_comparison: bool = True, tokenizer_override: str | None = None) -> dict[str, Any]:
    """Normalize run telemetry into per-run metrics.jsonl.

    With multiple runs, enforces compatibility between them. Returns the
    comparison dict. ``write_comparison`` controls whether a
    runs/comparison-*.json artifact is written (the compare command and
    analyze CLI write one; a single-run results view does not).
    """
    run_data = [read_json(path / "run.json") for path in run_paths]
    if len(run_data) > 1:
        compatible(run_data)
    identities = {tokenizer_identity(run) for run in run_data}
    tokenizers_comparable = tokenizer_override is not None or len(identities) <= 1
    tokenizer_path = tokenizer_override or next((tokenizer_path_from_run(run) for run in run_data if tokenizer_path_from_run(run)), None)
    shared_tokenizer = local_tokenizer(tokenizer_path) if tokenizers_comparable else None
    summaries = []
    for run_dir, run in zip(run_paths, run_data):
        raw = read_jsonl(run_dir / "raw.jsonl")
        normalized = normalize(run, raw, shared_tokenizer)
        write_jsonl(run_dir / "metrics.jsonl", normalized)
        summary = build_summary(run, normalized, run_dir)
        write_summary(run_dir / "summary.json", summary)
        summaries.append(summary)
    benchmark = {
        "name": run_data[0].get("benchmark"),
        "version": run_data[0].get("benchmark_version"),
    }
    models = list(dict.fromkeys(summary["model"] for summary in summaries if summary.get("model")))
    comparison = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "benchmark": benchmark,
        "run_ids": [summary["run_id"] for summary in summaries],
        "models": models,
        "execution_mode": execution,
        "official_comparison": execution == "sequential",
        "tokenizers_comparable": tokenizers_comparable,
        "runs": summaries,
    }
    if write_comparison:
        output = ROOT / "runs" / f"comparison-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
        output.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--execution", choices=("sequential", "parallel"), default="sequential", help="how provider runs were scheduled")
    parser.add_argument("--tokenizer", default=None, help="Exact tokenizer JSON path (overrides per-run tokenizer)")
    args = parser.parse_args()
    comparison = normalize_runs(args.runs, execution=args.execution, write_comparison=True, tokenizer_override=args.tokenizer)
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
