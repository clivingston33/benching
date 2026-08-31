#!/usr/bin/env python3
"""Extract real benchmark metrics from terminal-bench-results CSVs into
data/benchmark-summary.json consumed by the dashboard components.

Source: /home/caleb/terminal-bench-results on docker-24-04 (Jul 25-30 runs).
Canonical comparison runs (full, Terminal-Bench 2.1, 89 tasks):
  kourier     tb21-omp-kourier-full-qwen3.6-35b-20260729-051711  (qwen3.6-35b)
  electronhub tb21-omp-electronhub-full-glm-5.2-dev-20260725-225552 (glm-5.2:dev)

NOTE: the two canonical runs used DIFFERENT models per provider, so the
comparison is model-confounded. Kourier's proxy captured no token/usage
telemetry (ttft/decode/tokens are unavailable for kourier).
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "terminal-bench-results"
OUT = ROOT / "data" / "benchmark-summary.json"

CANON = {
    "kourier": "tb21-omp-kourier-full-qwen3.6-35b-20260729-051711",
    "electronhub": "tb21-omp-electronhub-full-glm-5.2-dev-20260725-225552",
}
MODELS = {"kourier": "qwen3.6-35b", "electronhub": "glm-5.2:dev"}


def load(name: str) -> list[dict]:
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))]


def median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


req = load("requests.csv")
tasks = load("tasks.csv")
runs = load("provider_runs.csv")


def provider_stats(prov: str) -> dict:
    rid = CANON[prov]
    rows = [r for r in req if r["run_id"] == rid]
    n = len(rows)
    ok = sum(1 for r in rows if r["http_status"] == "200")
    ttft = sorted(num(r["ttft_content_ms"]) for r in rows if num(r["ttft_content_ms"]) is not None)
    dec = [num(r["decode_wall_time_ms"]) for r in rows if num(r["decode_wall_time_ms"]) is not None]
    out = [num(r["output_tokens_reported"]) for r in rows if num(r["output_tokens_reported"]) is not None]
    durs = [num(r["request_duration_ms"]) for r in rows if num(r["request_duration_ms"]) is not None]
    inp = [num(r["input_tokens_reported"]) for r in rows if num(r["input_tokens_reported"]) is not None]
    cache = [num(r["cache_read_tokens_reported"]) for r in rows if num(r["cache_read_tokens_reported"]) is not None]
    timeouts = sum(1 for r in rows if r["http_status"] in ("524", "504"))
    stream_content = sum(
        1 for r in rows if r["http_status"] == "200" and num(r["content_chunk_count"]) and num(r["content_chunk_count"]) > 0
    )
    any_chunks_recorded = any(num(r["content_chunk_count"]) for r in rows)
    pairs = [(o, d) for o, d in zip(out, dec) if o and d and d > 0]
    tps = [o / d * 1000 for o, d in pairs]
    eff = [(o, d) for o, d in zip(out, durs) if o and d and d > 0]
    eff_tps = [o / d * 1000 for o, d in eff]
    return {
        "requests": n,
        "success_rate": round(ok / n * 100, 1) if n else None,
        "stream_completion_rate": round(stream_content / n * 100, 1) if n and any_chunks_recorded else None,
        "timeout_rate": round(timeouts / n * 100, 2) if n else None,
        "http_errors": n - ok,
        "median_ttft_ms": median(ttft),
        "p95_ttft_ms": pct(ttft, 0.95),
        "median_e2e_ms": median(durs),
        "median_decode_tps": median(tps),
        "median_effective_tps": median(eff_tps),
        "median_input_tokens": median(inp),
        "median_output_tokens": median(out),
        "median_cache_tokens": median(cache),
        "context_window": 262144,
        "http_statuses": dict(Counter(r["http_status"] for r in rows)),
    }


def task_pass_rate(prov: str) -> tuple[int, int, float | None]:
    rid = CANON[prov]
    rewards = []
    for t in tasks:
        if t["run_id"] != rid:
            continue
        try:
            vr = json.loads((t["verifier_result"] or "").replace("'", '"'))
        except Exception:
            continue
        if vr and "rewards" in vr and vr["rewards"].get("reward") is not None:
            rewards.append(float(vr["rewards"]["reward"]))
    passed = sum(1 for r in rewards if r == 1.0)
    rate = passed / len(rewards) * 100 if rewards else None
    return passed, len(rewards), rate


def run_history() -> list[dict]:
    out_runs = []
    for r in runs:
        if r["mode"] != "full" or r["provider"] not in ("kourier", "electronhub"):
            continue
        rid = r["run_id"]
        rows = [x for x in req if x["run_id"] == rid]
        ok = sum(1 for x in rows if x["http_status"] == "200")
        durs = [num(x["request_duration_ms"]) for x in rows if num(x["request_duration_ms"]) is not None]
        ttft = [num(x["ttft_content_ms"]) for x in rows if num(x["ttft_content_ms"]) is not None]
        dec = [num(x["decode_wall_time_ms"]) for x in rows if num(x["decode_wall_time_ms"]) is not None]
        out = [num(x["output_tokens_reported"]) for x in rows if num(x["output_tokens_reported"]) is not None]
        pairs = [(o, d) for o, d in zip(out, dec) if o and d and d > 0]
        tps = [o / d * 1000 for o, d in pairs]
        rewards = []
        for t in tasks:
            if t["run_id"] != rid:
                continue
            try:
                vr = json.loads((t["verifier_result"] or "").replace("'", '"'))
            except Exception:
                continue
            if vr and "rewards" in vr and vr["rewards"].get("reward") is not None:
                rewards.append(float(vr["rewards"]["reward"]))
        passed = sum(1 for x in rewards if x == 1.0)
        out_runs.append(
            {
                "id": rid,
                "date": r["created_at_utc"][:10],
                "provider": r["provider"],
                "model": r["model"],
                "requests": len(rows),
                "success_rate": round(ok / len(rows) * 100, 1) if rows else None,
                "median_e2e_ms": median(durs),
                "median_ttft_ms": median(ttft),
                "median_decode_tps": median(tps),
                "tasks_passed": passed,
                "tasks_total": len(rewards),
                "score": round(passed / len(rewards) * 100, 1) if rewards else None,
                "concurrency": r["concurrency"],
                "attempts": r["attempts"],
                "max_retries": r["max_retries"],
                "reasoning": r["reasoning"],
            }
        )
    return out_runs


def task_results() -> list[dict]:
    """Per-task pass/fail + tokens + duration for the 85 common tasks."""
    import ast
    import datetime

    def pl(s):
        try:
            return ast.literal_eval(s) if s else None
        except Exception:
            return None

    def parse_tasks(prov):
        rid = CANON[prov]
        m = {}
        for t in tasks:
            if t["run_id"] != rid:
                continue
            name = (t["task_name"] or "").replace("terminal-bench/", "")
            if not name:
                continue
            vr = pl(t["verifier_result"])
            ar = pl(t["agent_result"])
            ae = pl(t["agent_execution"])
            ei = pl(t["exception_info"])
            if not vr or "rewards" not in vr or vr["rewards"].get("reward") is None:
                continue

            def ts(s):
                try:
                    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    return None

            start, end = ts(ae.get("started_at", "")), ts(ae.get("finished_at", "")) if ae else (None, None)
            dur = (end - start).total_seconds() if start and end else None
            m[name] = {
                "passed": float(vr["rewards"]["reward"]) == 1.0,
                "duration_sec": dur,
                "input_tokens": num(ar.get("n_input_tokens")) if ar else None,
                "output_tokens": num(ar.get("n_output_tokens")) if ar else None,
                "cache_tokens": num(ar.get("n_cache_tokens")) if ar else None,
                "exception_type": ei.get("exception_type") if ei else None,
            }
        return m

    k = parse_tasks("kourier")
    e = parse_tasks("electronhub")
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


def context_scaling(prov: str) -> dict:
    """electronhub-only: bucket by reported input tokens."""
    rid = CANON[prov]
    rows = [r for r in req if r["run_id"] == rid]
    buckets = [("<16k", 0, 16000), ("16k-64k", 16000, 64000), ("64k+", 64000, 10**12)]
    out = {"speed": [], "ttft": [], "failure": []}
    for label, lo, hi in buckets:
        b = [r for r in rows if num(r["input_tokens_reported"]) is not None and lo <= num(r["input_tokens_reported"]) < hi]
        if not b:
            continue
        ttft = [num(r["ttft_content_ms"]) for r in b if num(r["ttft_content_ms"]) is not None]
        dec = [num(r["decode_wall_time_ms"]) for r in b if num(r["decode_wall_time_ms"]) is not None]
        out_t = [num(r["output_tokens_reported"]) for r in b if num(r["output_tokens_reported"]) is not None]
        pairs = [(o, d) for o, d in zip(out_t, dec) if o and d and d > 0]
        tps = [o / d * 1000 for o, d in pairs]
        err = sum(1 for r in b if r["http_status"] not in ("", "200"))
        out["speed"].append({"label": label, "electronhub": round(median(tps), 1) if tps else None})
        out["ttft"].append({"label": label, "electronhub": round(median(ttft)) if ttft else None})
        out["failure"].append({"label": label, "electronhub": round(err / len(b) * 100, 1)})
    return out


providers = {}
for prov in ("kourier", "electronhub"):
    s = provider_stats(prov)
    passed, total, rate = task_pass_rate(prov)
    s["tasks_passed"] = passed
    s["tasks_total"] = total
    s["task_pass_rate"] = round(rate, 1) if rate is not None else None
    providers[prov] = s

summary = {
    "generated_at": "2026-08-31",
    "source": "terminal-bench-results (Jul 25-30) on docker-24-04",
    "canonical_runs": CANON,
    "models": MODELS,
    "benchmark": "Terminal-Bench 2.1",
    "providers": providers,
    "run_history": run_history(),
    "task_results": task_results(),
    "context_scaling": {"electronhub": context_scaling("electronhub")},
    "notes": {
        "confound": "Canonical full runs used different models per provider (kourier=qwen3.6-35b, electronhub=glm-5.2:dev); the comparison is model-confounded, not a pure provider comparison.",
        "kourier_telemetry": "Kourier's proxy recorded no token/usage telemetry (TTFT, decode TPS, and token counts unavailable; n=0 of 3554 requests).",
        "stream_kourier": "Kourier stream completion unavailable (proxy recorded zero content chunks).",
        "context_window": "Both providers configured 262144 context window (262k).",
    },
}

OUT.write_text(json.dumps(summary, indent=2) + "\n")
print(f"wrote {OUT}")
print("providers:", {p: {k: v for k, v in s.items() if k != "http_statuses"} for p, s in providers.items()})
print("run_history:", len(summary["run_history"]), "task_results:", len(summary["task_results"]))
