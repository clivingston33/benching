#!/usr/bin/env python3
"""Build data/benchmark-summary.json with a per-run `runs` array.

Scans every comparison file in data/comparison-*.json (each represents one
completed two-provider run date) and emits one per-date record containing full
ProviderMetrics, context scaling, and per-task results for both providers.
The front-end then averages across `runs` by default or shows one run.

Data layout expected under data/:
  comparison-<ts>.json                     per-run comparison (both providers)
  full-runs/<run_id>.metrics.jsonl          per-request proxy telemetry
  full-runs/harbor-<run_id>/<task>.result.json    per-task harbor results (new layout)
  full-runs/harbor-<provider>/<task>.result.json  per-task harbor results (legacy layout)

Usage: python3 scripts/build-summary.py
"""
from __future__ import annotations

import datetime
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FULL = DATA / "full-runs"
OUT = DATA / "benchmark-summary.json"

PROVIDERS = ("kourier", "electronhub")
PROVIDER_LABELS = {"kourier": "Kourier", "electronhub": "ElectronHub"}
MODEL_LABEL = "DeepSeek V4 flash 0731"
CONTEXT_WINDOW = 262144

METRIC_FIELDS = [
    "requests",
    "success_rate",
    "stream_completion_rate",
    "timeout_rate",
    "http_errors",
    "provider_failures",
    "downstream_cancellations",
    "incomplete_provider_streams",
    "median_ttft_ms",
    "p95_ttft_ms",
    "median_e2e_ms",
    "median_decode_tps",
    "median_effective_tps",
    "median_input_tokens",
    "median_output_tokens",
    "median_cache_tokens",
    "context_window",
    "task_pass_rate",
]


def num(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def median_of(vals: list[object]) -> float | None:
    clean = [v for v in (num(x) for x in vals) if v is not None]
    return statistics.median(clean) if clean else None


def provider_stats(c: dict, run_id: str) -> dict:
    """Full ProviderMetrics for one provider record in a comparison file."""
    rel = c["reliability"]
    tim = c["timing"]
    tok = c["tokens"]
    reqs = c["requests"]
    # cache-token median from per-request telemetry when available
    cache = []
    metrics_file = FULL / f"{run_id}.metrics.jsonl"
    if metrics_file.exists():
        with metrics_file.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                v = m.get("tokens", {}).get("cache_read", {}).get("value")
                if v is not None:
                    cache.append(v)
    median_cache = median_of(cache) if cache else None

    def avg_tokens(field: str) -> float | None:
        total = tok.get(field)
        return round((total / reqs), 2) if total is not None and reqs else None

    return {
        "requests": reqs,
        "success_rate": round(rel["request_success_rate"] * 100, 2),
        "stream_completion_rate": round(rel["stream_completion_rate"] * 100, 2),
        "timeout_rate": round(rel["timeout_rate"] * 100, 2),
        "http_errors": rel.get("errors", 0) or 0,
        "provider_failures": rel.get("provider_failures", 0),
        "downstream_cancellations": rel.get("downstream_cancellations", 0),
        "incomplete_provider_streams": rel.get("incomplete_provider_streams", 0),
        "median_ttft_ms": round(tim["ttft_ms"]["median"], 2),
        "p95_ttft_ms": round(tim["ttft_ms"]["p95"], 2),
        "median_e2e_ms": round(tim["end_to_end_latency_ms"]["median"], 2),
        "median_decode_tps": round(tim["decode_tps"]["median"], 2),
        "median_effective_tps": round(tim["effective_tps"]["median"], 2),
        "median_input_tokens": avg_tokens("input_provider"),
        "median_output_tokens": avg_tokens("output_provider"),
        "median_cache_tokens": round(median_cache, 2) if median_cache is not None else None,
        "context_window": CONTEXT_WINDOW,
        "tasks_passed": c["benchmark"]["passed_tasks"],
        "tasks_total": c["benchmark"]["total_tasks"],
        "task_pass_rate": round(c["benchmark"]["score"] * 100, 1),
        "errors": rel.get("errors", 0),
    }


def load_tasks(run_id: str, provider: str) -> dict[str, dict]:
    """Per-task harbor results: new harbor-<run_id> layout or legacy harbor-<provider>."""
    out: dict[str, dict] = {}
    candidates = [FULL / f"harbor-{run_id}", FULL / f"harbor-{provider}"]
    for base in candidates:
        if not base.exists():
            continue
        for f in sorted(base.glob("*.result.json")):
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
            exc = d.get("exception_info") or {}
            start = end = None
            try:
                start = datetime.datetime.fromisoformat(str(d.get("started_at")).replace("Z", "+00:00"))
                end = datetime.datetime.fromisoformat(str(d.get("finished_at")).replace("Z", "+00:00"))
            except Exception:
                pass
            dur = (end - start).total_seconds() if start and end else None
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


def context_scaling(c: dict) -> dict:
    out = {}
    buckets = c.get("context_buckets") or {}
    speed, ttft, failure = [], [], []
    for label, b in buckets.items():
        if not b.get("requests"):
            continue
        speed.append({"label": label, "decode_tps": round(b["decode_tps"]["median"], 2)})
        ttft.append({"label": label, "ttft_ms": round(b["ttft_ms"]["median"], 2)})
        rate = b.get("success_rate")
        failure.append({"label": label, "failure_rate": None if rate is None else round((1 - rate) * 100, 2)})
    out["speed"] = speed
    out["ttft"] = ttft
    out["failure"] = failure
    return out


def task_results_pair(k: dict[str, dict], e: dict[str, dict]) -> list[dict]:
    common = sorted(set(k) & set(e))
    out = []
    for name in common:
        kd, ed = k[name], e[name]
        out.append({
            "task": name,
            "kourierPassed": kd["passed"],
            "electronPassed": ed["passed"],
            "kourierDurationSec": kd["duration_sec"],
            "electronDurationSec": ed["duration_sec"],
            "kourierInputTokens": kd["input_tokens"],
            "electronInputTokens": ed["input_tokens"],
            "kourierOutputTokens": kd["output_tokens"],
            "electronOutputTokens": ed["output_tokens"],
            "kourierCacheTokens": kd["cache_tokens"],
            "electronCacheTokens": ed["cache_tokens"],
            "kourierException": kd["exception_type"],
            "electronException": ed["exception_type"],
        })
    return out


def main() -> None:
    comparisons = sorted(DATA.glob("comparison-*.json"))
    if not comparisons:
        raise SystemExit("no comparison files in data/")

    # match each run_history id (provider+date) -> harbor/metrics sources via existing summary
    prior = json.loads(OUT.read_text()) if OUT.exists() else {}
    history = prior.get("run_history", [])
    # run id per (date, provider)
    id_by_date_prov = {(h["date"], h["provider"]): h["id"] for h in history}

    runs = []
    run_history_out = []
    for comp_path in comparisons:
        try:
            doc = json.loads(comp_path.read_text())
        except Exception:
            continue
        comp_runs = {r["provider"]: r for r in doc.get("runs", []) if isinstance(r, dict)}
        if not {"kourier", "electronhub"} <= set(comp_runs):
            continue
        date = (doc.get("created_at_utc") or "")[:10]
        if not date:
            continue
        providers_out = {}
        context_out = {}
        for prov in PROVIDERS:
            run_id = id_by_date_prov.get((date, prov))
            if not run_id:
                # fall back to a metrics file for this date+provider
                matches = sorted(FULL.glob(f"tb21-v1-{prov}-full-*"))
                candidates = [p for p in matches if (doc.get("created_at_utc") or "")[:10] in p.name or True]
                run_id = candidates[-1].name.replace(".metrics.jsonl", "") if candidates else f"{date}-{prov}"
            c = comp_runs[prov]
            providers_out[prov] = provider_stats(c, run_id)
            context_out[prov] = context_scaling(c)
        k = load_tasks(id_by_date_prov.get((date, "kourier"), ""), "kourier")
        e = load_tasks(id_by_date_prov.get((date, "electronhub"), ""), "electronhub")
        tasks = task_results_pair(k, e) if k and e else []
        model = doc.get("benchmark_model") or "deepseek-v4-flash-0731"
        runs.append({
            "date": date,
            "comparison": comp_path.name,
            "official_comparison": bool(doc.get("official_comparison")),
            "execution_mode": doc.get("provider_execution_mode") or "sequential",
            "model": model,
            "providers": providers_out,
            "context_scaling": context_out,
            "task_results": tasks,
        })
        for prov in PROVIDERS:
            run_history_out.append({
                "id": id_by_date_prov.get((date, prov)) or f"{date}-{prov}",
                "date": date,
                "provider": prov,
                "model": model,
                "requests": providers_out[prov]["requests"],
                "success_rate": providers_out[prov]["success_rate"],
                "median_e2e_ms": providers_out[prov]["median_e2e_ms"],
                "median_ttft_ms": providers_out[prov]["median_ttft_ms"],
                "median_decode_tps": providers_out[prov]["median_decode_tps"],
                "tasks_passed": providers_out[prov]["tasks_passed"],
                "tasks_total": providers_out[prov]["tasks_total"],
                "score": providers_out[prov]["task_pass_rate"],
                "mode": "full",
                "concurrency": "3",
                "reasoning": "default",
            })

    runs.sort(key=lambda r: r["date"])
    run_history_out.sort(key=lambda r: (r["date"], r["provider"]))

    summary = {
        "generated_at": datetime.date.today().isoformat(),
        "benchmark_model": runs[-1]["model"] if runs else "deepseek-v4-flash-0731",
        "models": {p: (runs[-1]["model"] if runs else "deepseek-v4-flash-0731") for p in PROVIDERS},
        "model_label": MODEL_LABEL,
        "benchmark": "Terminal-Bench 2.1 (full, 89 tasks)",
        "runs": runs,
        "run_history": run_history_out,
        "notes": {
            "averaging": "Headline metrics average across all full runs by default; use the run selector to view a single run.",
            "tokens": "Input/output tokens are provider-reported totals divided by request count; cache tokens are per-request medians from proxy telemetry.",
            "context_window": f"Both providers configured {CONTEXT_WINDOW} context window (262k).",
        },
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {OUT}")
    for r in runs:
        print(f"{r['date']}: kourier score={r['providers']['kourier']['task_pass_rate']}% electronhub={r['providers']['electronhub']['task_pass_rate']}% tasks={len(r['task_results'])}")


if __name__ == "__main__":
    main()
