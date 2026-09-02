"""Repository and runtime paths shared across the benchmark layer."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
CONFIG = ROOT / "config" / "benchmark.yaml"
CACHE_ROOT = Path.home() / ".cache" / "benching"
PROXY_PORT = 8765
DEFAULT_CONCURRENCY = 3
DEFAULT_TRIALS = 1

# Ensure user-local binaries (harbor, omp) resolve for subprocesses.
os.environ["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + os.environ.get("PATH", "")
