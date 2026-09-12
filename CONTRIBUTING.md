# Contributing to Benching

## Layout

```text
src/benching/   Python engine and CLI (benchmark orchestration, analytics,
                proxy, agents, Typer/shell UI)
dashboard/      Optional read-only Next.js viewer (no Python at runtime)
examples/       Canonical sanitized artifacts shared by contract tests
tests/          Python tests (unit + regression)
docs/           Artifact contract, publication policy, release gates
```

## Development setup

Python (3.12+):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install pytest build
python -m pytest -q
```

Dashboard (Node 22):

```bash
cd dashboard
npm ci
npm test
npm exec -- tsc --noEmit --incremental false
npm run build
```

Package check (from the repository root):

```bash
python -m build
```

## Architecture invariants

These are load-bearing; CI enforces most of them. Do not work around them.

```text
Python analytics owns metric semantics; the dashboard never recomputes
canonical metrics, it only validates and projects them.
summary.json / comparison-*.json are the portable public contract;
raw.jsonl, metrics.jsonl, run.json, logs, and credentials are private
(see docs/publication.md).
Reusable core (benchmark/) must not depend on CLI presentation
(no Rich/Typer imports); the dashboard must not require Python at runtime.
Result viewing stays read-only; only explicit reanalysis regenerates
artifacts. Comparisons never mutate standalone runs.
Schemas live only in src/benching/benchmark/schemas/; the dashboard
consumes them in place. Examples live only in examples/artifacts/.
Benchmark execution is Linux/WSL-only; analysis, CLI, and packaging stay
portable (Windows CI runs the same suite).
```

## Workflow

1. Branch, make a focused change with tests for behavior changes.
2. Run the checks matching your change (same commands CI runs):
   Python: `python -m pytest -q`; packaging touched: `python -m build`;
   dashboard: `npm test`, `tsc`, `next build` from `dashboard/`;
   schemas/examples/analytics/dashboard-lib touched: both sides.
3. Schema or example changes require producer *and* dashboard
   compatibility updates in the same PR.
4. Open a PR. Required CI must pass (see `docs/releasing.md` for the
   exact check names to require in branch protection).
5. Never commit secrets, provider keys, `.env` files (non-example),
   `runs/` output, or raw telemetry. The hygiene suite
   (`tests/test_release_hygiene.py`) scans the committed public corpus.

## Linting and secret scanning

There is deliberately no required lint gate in this milestone: no Python
linter/formatter is configured, and dashboard `npm run lint` is not wired
to a non-interactive gate, so CI does not run either. Do not add drive-by
reformatting to PRs.

Secret protection is the deterministic hygiene suite above (scans
committed fixtures/examples and distributions) plus the release-time
history review from M4 task 13. No third-party secret-scanning action is
wired yet: for a pre-alpha solo-maintainer repo the vetted fixture gates
cover the actual risk (committed example data), without granting a new
supply-chain dependency read access to every PR. Revisit when external
contributors arrive.
