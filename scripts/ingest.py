#!/usr/bin/env python3
"""Regenerate data/benchmark-summary.json for the benching-dashboard repo.

Run from a machine with SSH access to the benchmark server (docker-24-04).
It discovers the newest two-provider FULL comparison under the server's
provider-benchmark/runs/, copies the artifacts it needs into data/full-runs/,
then regenerates data/benchmark-summary.json in the dashboard's existing schema.

Usage:
    python3 scripts/ingest.py                 # newest two-provider comparison
    python3 scripts/ingest.py --compare 20260901-124952   # by date-stamp
    python3 scripts/ingest.py --no-fetch      # reuse data/full-runs artifacts
"""
from __future__ import annotations

import argparse
import datetime
import json
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FULL = DATA / "full-runs"
OUT = DATA / "benchmark-summary.json"

SERVER = "caleb@docker-24-04.netbird.selfhosted"
SERVER_HOME = "/home/caleb"  # remote server path (not local Path.home())
RUNS = Path(SERVER_HOME) / "provider-benchmark" / "runs"  # remote path passed to ssh/scp
MODEL_LABEL = "DeepSeek V4 flash 0731"
CONTEXT_WINDOW = 262144
PROVIDERS = ("kourier", "electronhub")


def remote(cmd: list[str]) -> str:
    return subprocess.check_output(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SERVER, *cmd],
        text=True,
    )


def remote_copy(remote_path: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         f"{SERVER}:{remote_path}", str(dest)]
    )


def newest_comparison() -> tuple[Path, str]:
    """Newest server comparison that includes both providers."""
    listing = remote(["ls", "-1", str(RUNS / "comparison-*.json")]).split()
    names = sorted((Path(n).name for n in listing), reverse=True)
    for name in names:
        body = remote(["cat", str(RUNS / name)])
        try:
            doc = json.loads(body)
        except Exception:
            continue
        provs = {r.get("provider") for r in doc.get("runs", []) if isinstance(r, dict)}
        if set(PROVIDERS) <= provs and doc.get("provider_execution_mode") in (None, "sequential"):
            return RUNS / name, name
    raise SystemExit("no two-provider sequential comparison found on server")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", default=None, help="server comparison filename (comparison-<ts>.json)")
    parser.add_argument("--no-fetch", action="store_true", help="reuse existing data/full-runs artifacts")
    args = parser.parse_args()

    if args.compare:
        name = args.compare if args.compare.endswith(".json") else f"comparison-{args.compare}.json"
        comp_path, name = RUNS / name, name
    else:
        comp_path, name = newest_comparison()

    comparison = json.loads(remote(["cat", str(comp_path)]))
    created = (comparison.get("created_at_utc") or "")[:10]
    benchmark_model = comparison.get("benchmark_model") or "deepseek-v4-flash-0731"
    exec_mode = comparison.get("provider_execution_mode") or "sequential"
    comp_runs = {r["provider"]: r for r in comparison["runs"] if isinstance(r, dict)}

    # --- discover each provider's run id (newest matching full run dir) ---
    run_ids: dict[str, str] = {}
    if args.no_fetch:
        for prov in PROVIDERS:
            matches = sorted(FULL.glob(f"harbor-tb21-v1-{prov}-full-*"))
            if not matches:
                raise SystemExit(f"no cached artifacts for {prov}; re-run without --no-fetch")
            run_ids[prov] = matches[-1].name[len("harbor-"):]
    else:
        for prov in PROVIDERS:
            listing = remote(["ls", "-1dt", str(RUNS / f"tb21-v1-{prov}-full-*")])
            run_id = Path(listing.splitlines()[0]).name
            run_ids[prov] = run_id
            # Copy metrics.jsonl
            remote_copy(RUNS / run_id / "metrics.jsonl", FULL / f"{run_id}.metrics.jsonl")
            # Copy per-task harbor result.json files, flattened to <task>.result.json
            dest = FULL / f"harbor-{run_id}"
            dest.mkdir(parents=True, exist_ok=True)
            listing = remote(["find", str(RUNS / run_id / "harbor" / run_id), "-maxdepth", "1", "-mindepth", "1", "-type", "d"])
            for trial_path in listing.splitlines():
                if not trial_path.strip():
                    continue
                trial = Path(trial_path).name
                task = trial.split("__", 1)[0]
                remote_copy(
                    RUNS / run_id / "harbor" / run_id / trial / "result.json",
                    dest / f"{task}.result.json",
                )
            print(f"fetched {prov}: {run_id} ({len(listing.splitlines())} trials)")

    # --- helpers (mirror the dashboard's expected summary schema) ---
    def num(v: object) -> float | None:
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def median_of(vals: list[object]) -> float | None:
        clean = [v for v in (num(x) for x in vals) if v is not None]
        return statistics.median(clean) if clean else None

    def load_metrics(run_id: str) -> list[dict]:
        rows = []
        with (FULL / f"{run_id}.metrics.jsonl").open() as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def load_tasks(run_id: str) -> dict[str, dict]:
        out = {}
        for f in (FULL / f"harbor-{run_id}").glob("*.result.json"):
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

    def provider_stats(run_id: str, c: dict) -> dict:
        rel = c["reliability"]
        tim = c["timing"]
        tok = c["tokens"]
        metrics = load_metrics(run_id)
        cache = [
            m["tokens"]["cache_read"]["value"]
            for m in metrics
            if m.get("tokens", {}).get("cache_read", {}).get("value") is not None
        ]
        return {
            "requests": c["requests"],
            "success_rate": round(rel["request_success_rate"] * 100, 1),
            "stream_completion_rate": round(rel["stream_completion_rate"] * 100, 1),
            "timeout_rate": round(rel["timeout_rate"] * 100, 2),
            "http_errors": rel.get("errors", 0) or 0,
            "provider_failures": rel.get("provider_failures", 0),
            "downstream_cancellations": rel.get("downstream_cancellations", 0),
            "incomplete_provider_streams": rel.get("incomplete_provider_streams", 0),
            "median_ttft_ms": tim["ttft_ms"]["median"],
            "p95_ttft_ms": tim["ttft_ms"]["p95"],
            "median_e2e_ms": tim["end_to_end_latency_ms"]["median"],
            "median_decode_tps": tim["decode_tps"]["median"],
            "median_effective_tps": tim["effective_tps"]["median"],
            "median_input_tokens": (tok.get("input_provider") or 0) / c["requests"] if tok.get("input_provider") else None,
            "median_output_tokens": (tok.get("output_provider") or 0) / c["requests"] if tok.get("output_provider") else None,
            "median_cache_tokens": median_of(cache),
            "context_window": CONTEXT_WINDOW,
            "tasks_passed": c["benchmark"]["passed_tasks"],
            "tasks_total": c["benchmark"]["total_tasks"],
            "task_pass_rate": round(c["benchmark"]["score"] * 100, 1),
            "errors": rel.get("errors", 0),
        }

    # --- build summary ---
    providers = {prov: provider_stats(run_ids[prov], comp_runs[prov]) for prov in PROVIDERS}

    def task_results() -> list[dict]:
        k = load_tasks(run_ids["kourier"])
        e = load_tasks(run_ids["electronhub"])
        common = sorted(set(k) & set(e))
        return [
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
            for name in common
        ]

    def run_history() -> list[dict]:
        return [
            {
                "id": run_ids[prov],
                "date": created,
                "provider": prov,
                "model": benchmark_model,
                "requests": comp_runs[prov]["requests"],
                "success_rate": providers[prov]["success_rate"],
                "median_e2e_ms": providers[prov]["median_e2e_ms"],
                "median_ttft_ms": providers[prov]["median_ttft_ms"],
                "median_decode_tps": providers[prov]["median_decode_tps"],
                "tasks_passed": providers[prov]["tasks_passed"],
                "tasks_total": providers[prov]["tasks_total"],
                "score": providers[prov]["task_pass_rate"],
                "mode": "full",
                "concurrency": "3",
                "reasoning": "default",
            }
            for prov in PROVIDERS
        ]

    def context_scaling() -> dict:
        out = {}
        for prov in PROVIDERS:
            buckets = comp_runs[prov].get("context_buckets") or {}
            speed, ttft, failure = [], [], []
            for label, b in buckets.items():
                if not b.get("requests"):
                    continue
                speed.append({"label": label, prov: b["decode_tps"]["median"]})
                ttft.append({"label": label, prov: b["ttft_ms"]["median"]})
                rate = b.get("success_rate")
                failure.append({"label": label, prov: None if rate is None else round((1 - rate) * 100, 1)})
            out[prov] = {"speed": speed, "ttft": ttft, "failure": failure}
        return out

    # --- preserve prior runs so the dashboard trend keeps history ---
    prior_history: list[dict] = []
    if OUT.exists():
        try:
            prior_history = json.loads(OUT.read_text()).get("run_history", [])
        except Exception:
            prior_history = []

    new_history = run_history()
    new_ids = {entry["id"] for entry in new_history}
    merged_history = [entry for entry in prior_history if entry["id"] not in new_ids] + new_history

    summary = {
        "generated_at": datetime.date.today().isoformat(),
        "source": f"provider-benchmark V1 FULL comparison {name} on docker-24-04",
        "benchmark_model": benchmark_model,
        "canonical_runs": run_ids,
        "models": {p: benchmark_model for p in PROVIDERS},
        "model_label": MODEL_LABEL,
        "benchmark": "Terminal-Bench 2.1 (full, 89 tasks)",
        "official_comparison": bool(comparison.get("official_comparison")),
        "provider_execution_mode": exec_mode,
        "providers": providers,
        "run_history": merged_history,
        "task_results": task_results(),
        "context_scaling": context_scaling(),
        "notes": {
            "apples_to_apples": f"Official V1 FULL comparison: same model {benchmark_model} on both providers, 89 Terminal-Bench 2.1 tasks each, completed {created}.",
            "tokens": "Input/output tokens are provider-reported totals divided by request count; cache tokens are per-request medians from proxy telemetry.",
            "context_window": f"Both providers configured {CONTEXT_WINDOW} context window (262k).",
            "request_counts": f"Kourier {comp_runs['kourier']['requests']} requests vs electronhub {comp_runs['electronhub']['requests']} — model calls per task vary with agent behavior.",
        },
    }

    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {OUT}")
    for p, s in providers.items():
        print(f"{p}: {s}")
    print("task_results:", len(summary["task_results"]))


if __name__ == "__main__":
    main()
