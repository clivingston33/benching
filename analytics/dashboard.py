#!/usr/bin/env python3
"""Build dashboard summary + CSV exports from a V1 comparison.

Reads the newest (or explicit) comparison-*.json under runs/, joins each
provider run's metrics.jsonl and harbor per-task results, and writes:

  dashboard/data/benchmark-summary.json  consumed by the Next.js dashboard
  reports/providers.csv                  per-provider aggregate metrics
  reports/tasks.csv                      per-task pass/fail + tokens + duration
  reports/requests.csv                   per-request telemetry rows

Works for any provider set in config/providers.yaml (1..N providers).
"""
from __future__ import annotations

import csv
import datetime
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
DASHBOARD_DATA = ROOT / "dashboard" / "data"
REPORTS = ROOT / "reports"
CONTEXT_WINDOW = 262144


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def latest_comparison(runs_root: Path = RUNS) -> Path:
    candidates = sorted(runs_root.glob("comparison-*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise SystemExit(f"no comparison-*.json found under {runs_root}; run `benchmarkctl compare` first")
    return candidates[-1]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_tasks(run_dir: Path) -> dict[str, dict]:
    """Per-task verifier results from harbor result.json files."""
    harbor = run_dir / "harbor"
    out = {}
    if not harbor.exists():
        return out
    for result in harbor.rglob("*result.json"):
        try:
            d = json.loads(result.read_text())
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


def provider_stats(c: dict, run_dir: Path) -> dict:
    rel = c.get("reliability") or {}
    tim = c.get("timing") or {}
    tok = c.get("tokens") or {}
    requests = c.get("requests") or 0
    metrics_path = run_dir / "metrics.jsonl"
    cache = []
    if metrics_path.exists():
        for m in read_jsonl(metrics_path):
            v = m.get("tokens", {}).get("cache_read", {}).get("value")
            if v is not None:
                cache.append(num(v))
    bench = c.get("benchmark") or {}
    return {
        "requests": requests,
        "success_rate": round(rel["request_success_rate"] * 100, 1) if rel.get("request_success_rate") is not None else None,
        "stream_completion_rate": round(rel["stream_completion_rate"] * 100, 1) if rel.get("stream_completion_rate") is not None else None,
        "timeout_rate": round(rel["timeout_rate"] * 100, 2) if rel.get("timeout_rate") is not None else None,
        "http_errors": rel.get("errors", 0) or 0,
        "provider_failures": rel.get("provider_failures", 0),
        "downstream_cancellations": rel.get("downstream_cancellations", 0),
        "incomplete_provider_streams": rel.get("incomplete_provider_streams", 0),
        "median_ttft_ms": tim.get("ttft_ms", {}).get("median"),
        "p95_ttft_ms": tim.get("ttft_ms", {}).get("p95"),
        "median_e2e_ms": tim.get("end_to_end_latency_ms", {}).get("median"),
        "median_decode_tps": tim.get("decode_tps", {}).get("median"),
        "median_effective_tps": tim.get("effective_tps", {}).get("median"),
        "median_input_tokens": (tok.get("input_provider") or 0) / requests if tok.get("input_provider") else None,
        "median_output_tokens": (tok.get("output_provider") or 0) / requests if tok.get("output_provider") else None,
        "median_cache_tokens": median(cache),
        "context_window": CONTEXT_WINDOW,
        "tasks_passed": bench.get("passed_tasks", 0),
        "tasks_total": bench.get("total_tasks", 0),
        "task_pass_rate": round(bench.get("score", 0) * 100, 1) if bench.get("score") is not None else None,
        "errors": rel.get("errors", 0),
    }


def run_dir_for(comparison: Path, run: dict) -> Path:
    rid = run.get("run_id")
    if rid:
        candidate = RUNS / rid
        if candidate.exists():
            return candidate
    # fallback: newest matching provider run dir
    candidates = sorted(RUNS.glob(f"tb21-v1-{run.get('provider')}-*"), key=lambda p: p.stat().st_mtime)
    if candidates:
        return candidates[-1]
    raise SystemExit(f"cannot locate run dir for provider {run.get('provider')} (run_id={rid})")


def build_summary(comparison_path: Path, out: Path) -> dict:
    comparison = json.loads(comparison_path.read_text())
    runs = comparison.get("runs", [])
    if not runs:
        raise SystemExit(f"comparison {comparison_path} has no runs")
    benchmark_model = comparison.get("benchmark_model") or runs[0].get("benchmark_model")
    models = {r.get("provider"): benchmark_model for r in runs}

    providers = {}
    run_history = []
    per_provider_tasks = {}
    for c in runs:
        prov = c.get("provider")
        run_dir = run_dir_for(comparison_path, c)
        providers[prov] = provider_stats(c, run_dir)
        tasks = load_tasks(run_dir)
        per_provider_tasks[prov] = tasks
        run_history.append(
            {
                "id": c.get("run_id") or run_dir.name,
                "date": (c.get("created_at_utc") or "")[:10] or comparison.get("created_at_utc", "")[:10],
                "provider": prov,
                "model": benchmark_model,
                "requests": c.get("requests", 0),
                "success_rate": providers[prov]["success_rate"],
                "median_e2e_ms": providers[prov]["median_e2e_ms"],
                "median_ttft_ms": providers[prov]["median_ttft_ms"],
                "median_decode_tps": providers[prov]["median_decode_tps"],
                "tasks_passed": providers[prov]["tasks_passed"],
                "tasks_total": providers[prov]["tasks_total"],
                "score": providers[prov]["task_pass_rate"],
                "mode": "full" if (providers[prov]["tasks_total"] or 0) > 10 else "smoke",
                "concurrency": str((run_dir / "run.json" and json.loads((run_dir / "run.json").read_text()).get("concurrency", "")) if (run_dir / "run.json").exists() else ""),
                "reasoning": "default",
            }
        )

    # task results: union of task names across providers
    all_tasks = sorted(set().union(*(set(t) for t in per_provider_tasks.values())))
    task_results = []
    for name in all_tasks:
        row = {"task": name}
        for prov in per_provider_tasks:
            t = per_provider_tasks[prov].get(name)
            row[f"{prov}Passed"] = t["passed"] if t else None
            row[f"{prov}DurationSec"] = t["duration_sec"] if t else None
            row[f"{prov}InputTokens"] = t["input_tokens"] if t else None
            row[f"{prov}OutputTokens"] = t["output_tokens"] if t else None
            row[f"{prov}CacheTokens"] = t["cache_tokens"] if t else None
            row[f"{prov}Exception"] = t["exception_type"] if t else None
        task_results.append(row)

    # context scaling per provider
    context_scaling = {}
    for prov, c in [(r.get("provider"), r) for r in runs]:
        buckets = c.get("context_buckets") or {}
        speed, ttft, failure = [], [], []
        for label, b in buckets.items():
            if not b.get("requests"):
                continue
            speed.append({"label": label, prov: b.get("decode_tps", {}).get("median")})
            ttft.append({"label": label, prov: b.get("ttft_ms", {}).get("median")})
            sr = b.get("success_rate")
            failure.append({"label": label, prov: (1.0 - sr) * 100 if sr is not None else None})
        context_scaling[prov] = {"speed": speed, "ttft": ttft, "failure": failure}

    summary = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": f"comparison {comparison_path.name} ({comparison.get('created_at_utc', '')})",
        "benchmark_model": benchmark_model,
        "canonical_runs": {r.get("provider"): (r.get("run_id") or "") for r in runs},
        "models": models,
        "model_label": benchmark_model,
        "benchmark": comparison.get("benchmark") or "Terminal-Bench 2.1",
        "official_comparison": comparison.get("official_comparison", False),
        "provider_execution_mode": comparison.get("provider_execution_mode", "sequential"),
        "providers": providers,
        "run_history": run_history,
        "task_results": task_results,
        "context_scaling": context_scaling,
        "notes": {
            "tokens": "Input/output tokens are provider-reported totals divided by request count; cache tokens are per-request medians from proxy telemetry.",
            "context_window": f"Both providers configured {CONTEXT_WINDOW} context window (262k).",
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def write_csvs(summary: dict, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written = []

    # providers.csv
    path = outdir / "providers.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary["providers"].values())[0].keys())
        writer.writeheader()
        for row in summary["providers"].values():
            writer.writerow(row)
    written.append(path)

    # tasks.csv
    path = outdir / "tasks.csv"
    with open(path, "w", newline="") as f:
        fieldnames = ["task"] + [k for k in summary["task_results"][0] if k != "task"] if summary["task_results"] else ["task"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary["task_results"]:
            writer.writerow(row)
    written.append(path)

    # run_history.csv
    path = outdir / "run_history.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary["run_history"][0].keys()) if summary["run_history"] else ["provider"])
        writer.writeheader()
        for row in summary["run_history"]:
            writer.writerow(row)
    written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dashboard summary + CSV exports from a comparison")
    parser.add_argument("--comparison", type=Path, default=None, help="comparison-*.json path (default: newest under runs/)")
    parser.add_argument("--csv-only", action="store_true", help="write CSVs only, skip dashboard summary")
    args = parser.parse_args()
    comparison = args.comparison or latest_comparison()
    summary = build_summary(comparison, DASHBOARD_DATA / "benchmark-summary.json")
    written = write_csvs(summary, REPORTS)
    print(f"comparison: {comparison}")
    print(f"providers: {', '.join(summary['providers'])}")
    if not args.csv_only:
        print(f"dashboard summary: {DASHBOARD_DATA / 'benchmark-summary.json'}")
    for path in written:
        print(f"csv: {path}")


if __name__ == "__main__":
    import argparse

    main()
