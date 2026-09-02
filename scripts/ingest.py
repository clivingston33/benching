#!/usr/bin/env python3
"""Fetch the newest benchmark comparison artifacts from the server into data/,
then regenerate data/benchmark-summary.json via scripts/build-summary.py.

Run from a machine with SSH access to the benchmark server (docker-24-04).
Copies: comparison JSON + per-run metrics.jsonl + per-task harbor result.json
files for each provider's newest full run, then rebuilds the summary (which the
dashboard averages across runs by default).

Usage:
    python3 scripts/ingest.py                       # newest two-provider comparison
    python3 scripts/ingest.py --compare 20260901-124952    # by date-stamp
    python3 scripts/ingest.py --no-fetch            # reuse existing data/ artifacts
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FULL = DATA / "full-runs"

SERVER = "caleb@docker-24-04.netbird.selfhosted"
SERVER_HOME = "/home/caleb"  # remote path, not local
RUNS = Path(SERVER_HOME) / "provider-benchmark" / "runs"

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
        try:
            doc = json.loads(remote(["cat", str(RUNS / name)]))
        except Exception:
            continue
        provs = {r.get("provider") for r in doc.get("runs", []) if isinstance(r, dict)}
        if set(PROVIDERS) <= provs:
            return RUNS / name, name
    raise SystemExit("no two-provider comparison found on server")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", default=None, help="server comparison filename (comparison-<ts>.json)")
    parser.add_argument("--no-fetch", action="store_true", help="reuse existing data/ artifacts")
    args = parser.parse_args()

    if args.compare:
        name = args.compare if args.compare.endswith(".json") else f"comparison-{args.compare}.json"
        comp_path, name = RUNS / name, name
    else:
        comp_path, name = newest_comparison()
    print(f"comparison: {name}")

    if not args.no_fetch:
        # Archive the comparison file itself.
        remote_copy(comp_path, DATA / name)
        # Discover + fetch each provider's newest full run artifacts.
        for prov in PROVIDERS:
            listing = remote(["ls", "-1dt", str(RUNS / f"tb21-v1-{prov}-full-*")])
            run_id = Path(listing.splitlines()[0]).name
            remote_copy(RUNS / run_id / "metrics.jsonl", FULL / f"{run_id}.metrics.jsonl")
            dest = FULL / f"harbor-{run_id}"
            dest.mkdir(parents=True, exist_ok=True)
            trial_listing = remote(["find", str(RUNS / run_id / "harbor" / run_id), "-maxdepth", "1", "-mindepth", "1", "-type", "d"])
            for trial_path in trial_listing.splitlines():
                if not trial_path.strip():
                    continue
                trial = Path(trial_path).name
                task = trial.split("__", 1)[0]
                remote_copy(
                    RUNS / run_id / "harbor" / run_id / trial / "result.json",
                    dest / f"{task}.result.json",
                )
            print(f"fetched {prov}: {run_id} ({len(trial_listing.splitlines())} trials)")

    # Regenerate the per-run summary.
    summary_script = ROOT / "scripts" / "build-summary.py"
    subprocess.check_call([sys.executable, str(summary_script)])


if __name__ == "__main__":
    main()
