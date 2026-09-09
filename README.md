# benching

Benchmark LLM API providers against terminal-agent task suites: run a task suite against one or more OpenAI-compatible providers behind a telemetry proxy, and compare latency, throughput, reliability, and task pass rates.

The installed package ships an immutable default benchmark manifest; user state, registered providers, credentials, and local benchmark manifests live under `~/.config/benching/` (overridable via `BENCHING_CONFIG_DIR`), and benchmark runs live under `./runs` (overridable via `BENCHING_RUNS_DIR`). Runtime data never lives inside the installed package.

## Layout

```text
cli/                       Typer command layer (thin: parse, call, render)
  app.py                   benching app + entry point
  shell.py                 interactive slash-command shell
  doctor.py                benching doctor
  config.py                benching config
  providers.py             provider management
  benchmarks.py            benchmark registry management
  runs.py                  benching runs
  results.py               benching results
  tokenizer.py             benching tokenizer
  run.py, compare.py       benching run / compare leaf commands
benchmark/                 execution and registry layers
  config.py                suite identity + merged provider config
  state.py                 persistent user defaults
  providers.py             provider registry mutations
  benchmarks.py             local benchmark manifests
  runner.py                run orchestration, harbor command, proxy lifecycle
  validation.py             provider preflight
  concurrency.py            staged concurrency probe
  tokenizer.py              pinned tokenizer cache
  _paths.py                shared repo/runtime paths
proxy/telemetry_proxy.py   OpenAI-compatible streaming proxy; per-run JSONL telemetry
analytics/analyze.py       normalize telemetry; build metrics.jsonl + comparison JSON
agents/instrumented_omp_agent.py  Harbor agent driving OMP through the proxy
benchmark/resources/     packaged immutable defaults (benchmark YAML, env example)
benchmark/schemas/       authoritative summary/comparison JSON Schemas
```

The CLI modules contain almost no benchmark logic: they parse arguments, call the `benchmark/` layer, and render results. A dashboard can import the same `benchmark/` functions.

## Requirements

- Python 3.12+, `docker`
- `harbor` and `omp` (see the org's setup docs); `harbor` must be on `PATH` and `omp` available inside the Harbor task image
- A provider serving an OpenAI-compatible streaming API

## Supported execution platform

Benchmark **execution** (`benching run`, `benching compare`, `/run`, `/smoke`,
`/compare`) requires **Linux or WSL** with working Docker, Harbor, and OMP.
Run lifecycle semantics (process-group termination, signal handling, Docker
bridge networking via `host.docker.internal`) are only known to work there;
on native Windows these commands fail fast with guidance instead of implying
support. Analysis and registry commands (`runs`, `results`, `tokenizer`,
`provider list`, `benchmark list`, `doctor`, `config`) remain portable.

Each run owns exactly its Harbor child, its telemetry-proxy child, its proxy
port, and its run directory. Interrupting a run (Ctrl+C) terminates the owned
Harbor work first and then the owned proxy with bounded waits, marks the run
`interrupted`, and never touches unrelated processes or containers. There is
no broad `docker stop $(docker ps -q)`-style cleanup anywhere.

The proxy binds `0.0.0.0` so task containers reach it via
`host.docker.internal`, and every request must present the run's random
`proxy_auth_token` (`X-Benchmark-Proxy-Auth` header, constant-time check).
Unauthenticated requests get `403` without telemetry or forwarding. The token
lives only in the private run directory: `proxy-auth.json` (mode 600) holds
the real token for the proxy child, while the persisted `command.json` record
stores `proxy_auth_token=[REDACTED]` (execution itself receives the real token
through its in-memory Harbor command). It never enters `run.json`, summaries,
or comparisons, and it is never logged.

## Run lifecycle and file publication

Run status moves through:

```text
created → running → analyzing → completed
```

with `failed` for Harbor/proxy/analysis/publication failures and
`interrupted` for Ctrl+C. `completed` means Harbor exited 0 **and** canonical
analysis succeeded **and** the required artifacts (`run.json`, `status.json`,
`metrics.jsonl`, `summary.json`) were published and verified. Harbor exit 0
alone only reaches `analyzing`. Analysis or publication failures keep all
evidence and record the phase (`analysis`/`publication`) plus a concise cause
in `status.json`; cleanup problems never overwrite that primary cause. A run
listed as `running`/`analyzing` whose owner process is gone on this host is
shown as stale (a read-only diagnostic; nothing is rewritten).

Application-owned complete JSON/YAML documents (status, run metadata,
summaries, comparisons, registries, user state, credentials) are published by
same-directory temp file plus `os.replace`, so readers only ever see the old
or the new complete document. Append-only evidence (`raw.jsonl`) is never
replaced mid-capture. Comparison files are named
`comparison-<UTC timestamp with microseconds>-<8 hex chars>.json`, so two
comparisons in the same second never share a path.

Simultaneous registry/state mutation from multiple shells or processes is
**not** a supported workflow: concurrent writers get last-writer-wins on
complete documents (never torn files), with no file locking. Malformed config
files are reported with their path and never silently replaced or truncated.

## Run independence and task accounting

Each run normalizes with its own recorded tokenizer context, so comparing
runs never rewrites their standalone `metrics.jsonl`/`summary.json`.
`benching results` only reads canonical artifacts; `benching results
reanalyze RUN` explicitly regenerates one run without touching comparisons.

Task accounting starts from planned work (`tasks` × `trials` in `run.json`):
every planned task is represented even with zero evidence, as a
`requests: 0` entry with null verdict fields — explicit absence, never a
fabricated failure. Multiple trials never collapse: status, live progress,
and summaries all key attempts by (task, trial). Duplicate request/result
identities fail analysis (identical repeats are deduplicated with a
warning); malformed telemetry or Harbor results fail with the file and line.
Numeric verifier rewards are preserved exactly; `passed` remains the derived
binary convenience (`reward == 1.0`).

Context buckets count requests by provider input tokens; requests with
unknown counts land in an explicit `unknown` bucket, so bucketed plus
unknown always equals the analyzed population. The concurrency probe reports
measured client-side overlap from real post-barrier request intervals — not
provider capacity. `environment_fingerprint` is a digest of the run record
for tamper-evidence, not proof of identical environments. Comparisons record
`tokenizer_identity_status` (`known_equal`/`known_different`/`unknown`; two
missing identities are unknown, never proven equal) alongside the
`tokenizers_comparable` boolean.

## Commands

```text
benching                         interactive shell
benching doctor                  environment health checks
benching config show             active suite, providers, and user defaults

benching provider list           providers with model + credential status
benching provider add            interactively register and validate a provider
benching provider remove <name>  remove a provider and its credential file
benching provider use <name>     persist the active provider
benching provider edit <name>    update URL, model, or API key
benching provider validate <name>
benching provider probe <name>

benching benchmark list          registered local Harbor suites
benching benchmark add           register a local task directory
benching benchmark remove <name>
benching benchmark use <name>    persist the active benchmark
benching benchmark info <name>

benching run [provider]           run the full suite
benching run [provider] --smoke   run the quick smoke subset
benching compare <a> <b>          run both, build comparison

benching runs                     list runs, newest first
benching results latest           show the latest result
benching tokenizer prepare        download the pinned tokenizer
```

`--help` is available at every level.

## Configure a benchmark suite

The packaged default manifest declares everything suite-specific (see
`benchmark/resources/benchmark.yaml` for the exact shipped content):

```yaml
benchmark:
  name: my-suite
  version: "1.0"
  model: model-identifier            # optional benchmark default; /model overrides it
  reasoning: default                 # run default; /reasoning overrides it
  tasks_dir: ~/my-suite/tasks        # one subdirectory per task
  expected_task_count: 50            # full mode asserts this many tasks
  smoke_tasks: [task-a, task-b]      # quick subset for smoke mode
  agent: benching.agents.instrumented_omp_agent:InstrumentedOmpAgent
  max_tokens: 49152
  context_window: 262144
  run_id_prefix: my-suite
  tokenizer:                         # pinned local-count tokenizer
    repo: org/tokenizer
    revision: <sha>
    env_override: TOKENIZER_PATH     # optional local override var
```

Point `tasks_dir` at a directory whose subdirectories are tasks. The optional model and reasoning values are defaults; each run may select a provider model and reasoning mode independently.

## Configure providers

Interactive provider management writes:

```text
~/.config/benching/
  config.yaml                 active provider/benchmark and run defaults
  providers.yaml              provider metadata (no keys)
  providers/<name>.env        credentials, mode 600 where supported
  benchmarks/<name>.yaml      local BenchmarkSpec manifests
```

Provider metadata may carry model-specific execution defaults; secrets remain
the only contents of the provider env file:

```yaml
default_model: accounts/example/deepseek
model_defaults:
  tokenizer:
    repo: deepseek-ai/DeepSeek-V4-Flash-0731
    revision: <sha>
  context_window: 262144
  max_tokens: 49152
```

Add and activate a provider without editing YAML:

```bash
benching provider add
benching provider list
benching provider validate <name>
benching provider use <name>
```

The packaged default manifest remains the fallback suite manifest.
Registered local suites overlay it when selected with `benching benchmark use`.

## Runtime paths

```text
package resources   benchmark/resources/, benchmark/schemas/ (read-only, in the wheel)
user config         ~/.config/benching/ or BENCHING_CONFIG_DIR (writable)
runs                ./runs or BENCHING_RUNS_DIR (writable, never site-packages)
caches              ~/.cache/benching/ (disposable)
```

Relative `tasks_dir` and credential `env_file` paths resolve against the
invoking working directory. Importing Benching never modifies the parent
process environment; `~/.local/bin` is consulted explicitly when resolving
`harbor`/`omp` and building child subprocess environments. Simultaneous
registry mutation from multiple processes is unsupported (last-writer-wins
on complete documents, no locking).

## Quickstart

```bash
python3 -m pip install -e .
benching doctor
benching tokenizer prepare
benching provider add
benching provider use myprovider
benching run --smoke
```

Smoke validates credentials, runs the smoke tasks, and produces a run under `runs/`.

## Run artifacts

Each run is isolated under `runs/<run-id>/`:

```text
run.json                 immutable execution metadata and fingerprint
status.json              lifecycle status
command.json             exact runner command
proxy-routes.json        trusted upstream routing configuration
raw.jsonl                raw proxy telemetry
metrics.jsonl            normalized request-level analytics
summary.json             self-contained dashboard run contract
*.log                    runner and proxy logs
```

`run.json` is immutable execution metadata. `raw.jsonl` preserves proxy
telemetry as captured. `metrics.jsonl` is the detailed normalized
request-level analytics artifact. `summary.json` is intentionally
self-contained for external consumers: it contains run-level metrics, context
buckets, and one aggregated outcome per benchmark task/trial, including
Harbor verifier fields and telemetry aggregates. It does not replace
`metrics.jsonl`.

Comparison artifacts under `runs/comparison-*.json` are the canonical
multi-run contract. They use schema version 1 and contain benchmark identity,
run IDs, selected models, execution mode, tokenizer comparability, and
embedded completed `summary.json` documents. Provider-specific comparison
fields do not belong in this artifact.

Schema version 1 is retained: the canonical summary/comparison artifacts were
introduced in the current release line, so task-level aggregation and context
buckets complete that contract without a second externally released schema.
Authoritative JSON Schemas live in `schemas/`; see `docs/artifacts.md` for
the public/private boundary, versioning, units, null semantics, and support
promise. Sanitized producer examples live in `examples/artifacts/`.

## Metric definitions

```text
TTFT = first semantic output - request_started
Decode duration = last semantic output - first semantic output
End-to-end latency = stream_completed - request_started
Decode TPS = locally counted output tokens / decode duration seconds
Effective TPS = locally counted output tokens / end-to-end latency seconds
CV = standard_deviation / mean
```

Semantic output is model-generated text in a supported shape: visible text
content, reasoning/thinking text, and tool/function-call names plus their
argument text, in streamed order. Role-only deltas, empty content, usage-only
events, `[DONE]`, and finish-reason-only events are protocol metadata, not
semantic output, and never move first/last-output timing. A request counts as
successful only with a supported terminal condition (`[DONE]`, a
finish/stop reason, or parsed non-SSE content) and no provider error; EOF
alone never proves success. Each proxied request records exactly one
`completion_status`: `ok`, `http_error`, `provider_error`, `truncated`,
`protocol_error`, `timeout`, `cancelled`, `connection_error`, or `error`.
Partial output from failed requests is retained as evidence but never counts
toward success. Shapes that cannot be safely normalized into countable text
leave local token metrics explicitly unavailable instead of reporting a
misleading zero.

Provider-reported usage is stored separately from locally calculated output tokens. Local tokenization uses `tokenizers.Tokenizer` against the pinned tokenizer cache. If the exact tokenizer is unavailable or output capture is truncated, local-token metrics are explicitly unavailable. Cache metrics are never estimated; missing provider cache fields remain unavailable. Agent-side Harbor usage keeps the provider input total as reported (OpenAI-style prompt totals already include cached tokens) with cache tokens reported separately.

## Architecture

```text
Task suite -> Harbor -> OMP -> telemetry proxy -> provider HTTPS API
                                        |
                                        +-> run-scoped raw.jsonl

analytics/analyze.py -> metrics.jsonl and comparison JSON
```

A live progress dashboard is a later milestone: `benchmark.runner.run_one` already reports deterministic `(phase, message)` progress events through an optional callback, and the CLI renders them as status lines; a dashboard can subscribe to the same hook.

## History

This repository previously hardcoded a Terminal-Bench 2.1 comparison of the Kourier and ElectronHub providers and was renamed from `provider-benchmark` to `benching`. It now ships as a generic harness; the earlier `benchmarkctl` command line was replaced by the `benching` hierarchy.
