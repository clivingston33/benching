#!/usr/bin/env python3
"""Extract real benchmark metrics from the V1 apples-to-apples comparison
into data/benchmark-summary.json consumed by the dashboard components.

Source: provider-benchmark V1 on docker-24-04 (2026-08-31 runs).
Official comparison: comparison-20260831-203259.json
  benchmark_model: deepseek-v4-flash-0731  (same model both providers)
  kourier     tb21-v1-kourier-smoke-20260831-200149-09964eee   (96 req)
  electronhub tb21-v1-electronhub-smoke-20260831-201746-45a7c8b2 (26 req)
  Terminal-Bench 2.1, sequential, 3 smoke tasks, official_comparison: true
"""
from __future__ import annotations

import datetime
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
V1 = DATA / "v1-runs"
COMPARISON = DATA / "comparison-20260831-203259.json"
OUT = DATA / "benchmark-summary.json"

MODELS = {"kourier": "deepseek-v4-flash-0731", "electronhub": "deepseek-v4-flash-0731"}
MODEL_LABEL = "DeepSeek V4 flash 0731"
CONTEXT_WINDOW = 262144

RUNS = {
    "kourier": "tb21-v1-kourier-smoke-20260831-200149-09964eee",
    "electronhub": "tb21-v1-electronhub-smoke-20260831-201746-45a7c8b2",
}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def load_metrics(prov: str) -> list[dict]:
    rows = []
    with open(V1 / f"{RUNS[prov]}.metrics.jsonl") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_tasks(prov: str) -> dict[str, dict]:
    """Per-task verifier results from harbor result.json (one per task)."""
    harbor_dir = V1 / f"{prov}-harbor"
    out = {}
    for f in harbor_dir.glob("*.result.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        name = (d.get("task_name") or "").replace("terminal-bench/", "")
        if not name:
            continue
        reward = None
        if d.get("verifier_result") and "rewards" in d["verifier_result"]:
            reward = d["verifier_result"]["rewards"].get("reward")
        ar = d.get("agent_result") or {}

        def ts(s):
            try:
                return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return None

        start, end = ts(d.get("started_at")), ts(d.get("finished_at"))
        dur = (end - start).total_seconds() if start and end else None
        exc = d.get("exception_info") or {}
        out[name] = {
            "passed": reward == 1.0,
            "reward": reward,
            "duration_sec": dur,
            "input_tokens": num(ar.get("n_input_tokens")),
            "output_tokens": num(ar.get("n_output_tokens")),
            "cache_tokens": num(ar.get("n_cache_tokens")),
            "exception_type": exc.get("exception_type"),
        }
    return out


comparison = json.loads(COMPARISON.read_text())
runs = {r["provider"]: r for r in comparison["runs"]}


def provider_stats(prov: str) -> dict:
    c = runs[prov]
    rel = c["reliability"]
    tim = c["timing"]
    tok = c["tokens"]
    metrics = load_metrics(prov)
    # per-request medians for cache tokens (not in comparison aggregate)
    cache = [num(m["tokens"]["cache_read"]["value"]) for m in metrics if m.get("tokens", {}).get("cache_read", {}).get("value") is not None]
    return {
        "requests": c["requests"],
        "success_rate": round(rel["request_success_rate"] * 100, 1),
        "stream_completion_rate": round(rel["stream_completion_rate"] * 100, 1),
        "timeout_rate": round(rel["timeout_rate"] * 100, 2),
        "http_errors": rel.get("http_errors", 0) or 0,
        "median_ttft_ms": tim["ttft_ms"]["median"],
        "p95_ttft_ms": tim["ttft_ms"]["p95"],
        "median_e2e_ms": tim["end_to_end_latency_ms"]["median"],
        "median_decode_tps": tim["decode_tps"]["median"],
        "median_effective_tps": tim["effective_tps"]["median"],
        "median_input_tokens": (tok.get("input_provider") or 0) / c["requests"] if tok.get("input_provider") else None,
        "median_output_tokens": (tok.get("output_provider") or 0) / c["requests"] if tok.get("output_provider") else None,
        "median_cache_tokens": median(cache),
        "context_window": CONTEXT_WINDOW,
        "tasks_passed": c["benchmark"]["passed_tasks"],
        "tasks_total": c["benchmark"]["total_tasks"],
        "task_pass_rate": round(c["benchmark"]["score"] * 100, 1),
        "errors": rel.get("errors", 0),
        "downstream_cancellations": rel.get("downstream_cancellations", 0),
    }


def task_results() -> list[dict]:
    k = load_tasks("kourier")
    e = load_tasks("electronhub")
    common = sorted(set(k) & set(e))
    results = []
    for name in common:
        results.append(
            {
                "task": name,
                "kourierPassed": k[name]["passed"],
                "electronPassed": e[name]["passed"],
                "kourierDurationSec": k[name]["duration_sec"],
                "electronDurationSec": e[name]["duration_sec"],
                "kourierInputTokens": k[name]["input_tokens"],
                "electronInputTokens": e[name]["input_tokens"],
                "kourierOutputTokens": k[name]["output_tokens"],
                "electronOutputTokens": e[name]["output_tokens"],
                "kourierCacheTokens": k[name]["cache_tokens"],
                "electronCacheTokens": e[name]["cache_tokens"],
                "kourierException": k[name]["exception_type"],
                "electronException": e[name]["exception_type"],
            }
        )
    return results


def run_history() -> list[dict]:
    """The two official comparison runs (Aug 31)."""
    out = []
    for prov in ("kourier", "electronhub"):
        c = runs[prov]
        s = provider_stats(prov)
        out.append(
            {
                "id": RUNS[prov],
                "date": c["created_at_utc"][:10] if "created_at_utc" in c else "2026-08-31",
                "provider": prov,
                "model": MODELS[prov],
                "requests": c["requests"],
                "success_rate": s["success_rate"],
                "median_e2e_ms": s["median_e2e_ms"],
                "median_ttft_ms": s["median_ttft_ms"],
                "median_decode_tps": s["median_decode_tps"],
                "tasks_passed": s["tasks_passed"],
                "tasks_total": s["tasks_total"],
                "score": s["task_pass_rate"],
                "concurrency": "sequential",
                "attempts": c["benchmark"].get("retries", 0),
                "mode": "smoke",
                "reasoning": comparison.get("provider_execution_mode", "sequential"),
            }
        )
    return out


def context_scaling() -> dict:
    """Per-provider context buckets from the comparison (TTFT / decode TPS)."""
    out = {}
    for prov in ("kourier", "electronhub"):
        buckets = runs[prov]["context_buckets"]
        speed, ttft, failure = [], [], []
        for label, b in buckets.items():
            if not b.get("requests"):
                continue
            speed.append({"label": label, prov: b["decode_tps"]["median"]})
            ttft.append({"label": label, prov: b["ttft_ms"]["median"]})
            fail_rate = 1.0 - (b.get("success_rate") or 0) if b.get("success_rate") is not None else None
            failure.append({"label": label, prov: fail_rate * 100 if fail_rate is not None else None})
        out[prov] = {"speed": speed, "ttft": ttft, "failure": failure}
    return out


providers = {}
for prov in ("kourier", "electronhub"):
    providers[prov] = provider_stats(prov)

summary = {
    "generated_at": "2026-08-31",
    "source": "provider-benchmark V1 official comparison (2026-08-31) on docker-24-04",
    "benchmark_model": "deepseek-v4-flash-0731",
    "canonical_runs": RUNS,
    "models": MODELS,
    "model_label": MODEL_LABEL,
    "benchmark": "Terminal-Bench 2.1 (smoke, 3 tasks)",
    "official_comparison": comparison.get("official_comparison", True),
    "provider_execution_mode": comparison.get("provider_execution_mode", "sequential"),
    "providers": providers,
    "run_history": run_history(),
    "task_results": task_results(),
    "context_scaling": context_scaling(),
    "notes": {
        "apples_to_apples": "Official V1 comparison: same model deepseek-v4-flash-0731 on both providers (kourier api_model DSV4-Flash-0731, electronhub api_model deepseek-v4-flash-0731:dev).",
        "smoke": "Smoke run — 3 Terminal-Bench 2.1 tasks per provider (adaptive-rejection-sampler, break-filter-js-from-html, cancel-async-tasks), sequential, 1 attempt, no retries.",
        "tokens": "Input/output tokens are provider-reported totals divided by request count; cache tokens are per-request medians from proxy telemetry.",
        "context_window": f"Both providers configured {CONTEXT_WINDOW} context window (262k).",
        "kourier_requests": "Kourier ran 96 requests vs electronhub 26 — kourier's adaptive-rejection-sampler task timed out (AgentTimeoutError) with many retried calls.",
    },
}

OUT.write_text(json.dumps(summary, indent=2) + "\n")
print(f"wrote {OUT}")
for p, s in providers.items():
    print(f"{p}: {s}")
print("task_results:", len(summary["task_results"]))
