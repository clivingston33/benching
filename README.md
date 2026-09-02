# benching

Generic LLM-provider benchmarking harness: run a terminal-agent task suite against one or more OpenAI-compatible providers behind a telemetry proxy, and compare latency, throughput, reliability, and task pass rates.

Suite and provider identity live entirely in `config/benchmark.yaml`; nothing in the code is specific to any one benchmark or provider.

## Layout

```text
benchmark/benchmarkctl.py    CLI runner (smoke / full / validate / probe-concurrency / compare)
benchmark/concurrency_probe.py  direct staged concurrency-capability probe
proxy/telemetry_proxy.py     OpenAI-compatible streaming proxy; per-run JSONL telemetry
analytics/analyze.py         normalize telemetry; build metrics.jsonl and comparison JSON
agents/instrumented_omp_agent.py  Harbor agent driving OMP through the proxy
config/benchmark.yaml        benchmark suite identity + provider registry
config/provider.env.example  template for a provider credential file
```

## Requirements

- Python 3.12+, `docker`
- `harbor` and `omp` (see the org's setup docs); `harbor` must be on `PATH` and `omp` available inside the Harbor task image
- A provider serving an OpenAI-compatible streaming API

## Configure a benchmark suite

`config/benchmark.yaml` declares everything suite-specific:

```yaml
benchmark:
  name: my-suite
  version: "1.0"
  model: model-identifier            # canonical benchmark model
  reasoning: default                 # default | enabled | disabled
  tasks_dir: ~/my-suite/tasks        # one subdirectory per task
  expected_task_count: 50            # full mode asserts this many tasks
  smoke_tasks: [task-a, task-b]      # quick subset for smoke mode
  agent: agents.instrumented_omp_agent:InstrumentedOmpAgent
  max_tokens: 49152
  context_window: 262144
  run_id_prefix: my-suite
  tokenizer:                         # pinned local-count tokenizer
    repo: org/tokenizer
    revision: <sha>
    env_override: TOKENIZER_PATH     # optional local override var
```

Point `tasks_dir` at a directory whose subdirectories are tasks, set the canonical model and tokenizer, and the harness uses them everywhere (run metadata, validation, comparison compatibility).

## Configure providers

Enable one or more providers under `providers:` in `config/benchmark.yaml`:

```yaml
providers:
  myprovider:
    enabled: true
    env_file: config/myprovider.env
    auth_env: MYPROVIDER_API_KEY
    base_url: https://api.myprovider.com/v1
    api_model: provider-specific-model-id
    api: openai-completions
    strict_model_check: false
    plan: null
    plan_tier: unknown
    routing_entitlement: null
    benchmark_concurrency_limit: null
```

Create the matching credential file from the template:

```bash
cp config/provider.env.example config/myprovider.env
chmod 600 config/myprovider.env
# set MYPROVIDER_API_KEY (and optionally MYPROVIDER_BASE_URL / MYPROVIDER_API_MODEL,
# which override base_url / api_model)
```

`<NAME>_BASE_URL` and `<NAME>_API_MODEL` in the env file override the YAML values; the YAML `auth_env` names the key the harness reads.

No code changes are needed; enabled providers are picked up automatically by `validate`, `smoke`, `full`, `probe-concurrency`, and `compare`. Set `strict_model_check: true` to require `api_model` in the provider's `/models` catalog during validation.

## Quickstart

```bash
python3 -m pip install -e .
cp config/provider.env.example config/myprovider.env   # then fill in the key
chmod 600 config/myprovider.env
benchmarkctl prepare-tokenizer     # cache the pinned tokenizer once
benchmarkctl smoke --provider myprovider
```

That validates credentials, runs the smoke tasks, and produces a run under `runs/`.

## Commands

```bash
benchmarkctl prepare-tokenizer
benchmarkctl validate --provider myprovider
benchmarkctl probe-concurrency --provider myprovider
benchmarkctl smoke --provider myprovider
benchmarkctl full --provider myprovider
benchmarkctl compare --providers myprovider,otherprovider --concurrency 3
benchmarkctl compare --providers myprovider,otherprovider --execution parallel --concurrency 3
```

Each command:

- `prepare-tokenizer` — downloads the pinned tokenizer (`tokenizer.json`, config, etc.) into the local cache once, if not already present. Runs use the cache read-only and never re-download.
- `validate --provider <name>` — checks credentials and that the provider serves the configured model over streaming; every run re-validates first.
- `probe-concurrency --provider <name> [--stages 2,3,5,6]` — stages direct concurrent-stream requests to find the provider's concurrency ceiling, stopping at the first rejected stage; doesn't touch benchmark scores.
- `smoke --provider <name>` — runs the configured smoke tasks to confirm the pipeline.
- `full --provider <name>` — runs the full suite; the real benchmark.
- `compare --providers <a>,<b> [--execution sequential|parallel]` — runs the given mode for each provider, then builds the comparison report. `sequential` (default) runs providers one at a time so they don't compete for host resources — the official, comparable mode. `parallel` runs them concurrently for informal/faster testing. The comparison JSON records `provider_execution_mode` and sets `official_comparison: false` for parallel runs, so a host-contention run can't be mistaken for an official comparison. `--parallel-providers` remains as an alias for `--execution parallel`.

Validation is authoritative; smoke and full runs refuse to start when provider preflight fails.

Reasoning is an explicit mode — `default`, `enabled`, or `disabled`. `default` injects no override, so the provider/model behaves normally; `disabled` makes the proxy inject `reasoning.enabled=false`; `enabled` sets it true. The mode is recorded as `reasoning_mode` in `run.json`.

## Run artifacts

Each run is isolated under `runs/<run-id>/`:

```text
run.json                 immutable run configuration and fingerprint
status.json              lifecycle status
command.json             exact runner command
proxy-routes.json        trusted upstream routing configuration
raw.jsonl                proxy telemetry and captured debug data
metrics.jsonl            normalized analytical records
harbor/                  runner task artifacts
*.log                    runner and proxy logs
```

## Metric definitions

```text
TTFT = first_content_output - request_started
Decode duration = last_content_output - first_content_output
End-to-end latency = stream_completed - request_started
Decode TPS = locally counted output tokens / decode duration seconds
Effective TPS = locally counted output tokens / end-to-end latency seconds
CV = standard_deviation / mean
```

Provider-reported usage is stored separately from locally calculated output tokens. Local tokenization uses `tokenizers.Tokenizer` against the pinned tokenizer cache. If the exact tokenizer is unavailable or output capture is truncated, local-token metrics are explicitly unavailable. Cache metrics are never estimated; missing provider cache fields remain unavailable.

## Architecture

```text
Task suite -> Harbor -> OMP -> telemetry proxy -> provider HTTPS API
                                        |
                                        +-> run-scoped raw.jsonl

analytics/analyze.py -> metrics.jsonl and comparison JSON
```

## Rebranding history

This repository previously hardcoded a Terminal-Bench 2.1 comparison of the Kourier and ElectronHub providers and was renamed from `provider-benchmark`. It now ships as a generic harness (this branch, `standardize/generic-benchmark-harness`); a follow-up is planned to expose the same functionality as a unified CLI.
