# benching

Benchmark LLM API providers against terminal-agent task suites: run a task suite against one or more OpenAI-compatible providers behind a telemetry proxy, and compare latency, throughput, reliability, and task pass rates.

Suite and provider identity live entirely in `config/benchmark.yaml`; nothing in the code is specific to any one benchmark or provider.

## Layout

```text
cli/                       Typer command layer (thin: parse, call, render)
  app.py                   benching app + entry point
  doctor.py                benching doctor
  config.py                benching config
  providers.py             benching provider
  runs.py                  benching runs
  results.py               benching results
  tokenizer.py             benching tokenizer
  run.py, compare.py       benching run / compare leaf commands
benchmark/                 execution layer (importable by a dashboard)
  config.py                suite identity + provider registry from config
  runner.py                run orchestration, harbor command, proxy lifecycle
  validation.py            provider preflight
  concurrency.py           staged concurrency probe
  tokenizer.py             pinned tokenizer cache
  _paths.py                shared repo/runtime paths
proxy/telemetry_proxy.py   OpenAI-compatible streaming proxy; per-run JSONL telemetry
analytics/analyze.py       normalize telemetry; build metrics.jsonl + comparison JSON
agents/instrumented_omp_agent.py  Harbor agent driving OMP through the proxy
config/benchmark.yaml      benchmark suite identity + provider registry
config/provider.env.example  template for a provider credential file
```

The CLI modules contain almost no benchmark logic: they parse arguments, call the `benchmark/` layer, and render results. A dashboard can import the same `benchmark/` functions.

## Requirements

- Python 3.12+, `docker`
- `harbor` and `omp` (see the org's setup docs); `harbor` must be on `PATH` and `omp` available inside the Harbor task image
- A provider serving an OpenAI-compatible streaming API

## Commands

```text
benching doctor                    environment health checks
benching config show               suite identity + provider registry

benching provider list             providers with model + credential status
benching provider validate <name>  credentials + streaming model access
benching provider probe <name>     concurrency ceiling probe

benching run <provider>            run the full suite
benching run <provider> --smoke    run the quick smoke subset
benching run <provider> --concurrency 3

benching compare <a> <b>           run both, build comparison
benching compare <a> <b> --execution parallel

benching runs                      list runs, newest first
benching runs show <run-id>        run config (prefix or 'latest' accepted)
benching runs latest

benching results show <run-id>     latency / reliability / task tables
benching results latest

benching tokenizer prepare         download the pinned tokenizer
benching tokenizer status          cached?
```

`--help` is available at every level.

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

No code changes are needed; enabled providers are picked up automatically by `provider list` / `provider validate` / `provider probe`, `run`, and `compare`. Set `strict_model_check: true` to require `api_model` in the provider's `/models` catalog during validation.

## Quickstart

```bash
python3 -m pip install -e .
cp config/provider.env.example config/myprovider.env   # then fill in the key
chmod 600 config/myprovider.env
benching doctor                     # confirm the environment is ready
benching tokenizer prepare          # cache the pinned tokenizer once
benching provider validate myprovider
benching run myprovider --smoke
```

Smoke validates credentials, runs the smoke tasks, and produces a run under `runs/`.

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

`benching runs` lists these; `benching results show` reads them. Run-id prefixes and `latest` resolve automatically.

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

A live progress dashboard is a later milestone: `benchmark.runner.run_one` already reports deterministic `(phase, message)` progress events through an optional callback, and the CLI renders them as status lines; a dashboard can subscribe to the same hook.

## History

This repository previously hardcoded a Terminal-Bench 2.1 comparison of the Kourier and ElectronHub providers and was renamed from `provider-benchmark` to `benching`. It now ships as a generic harness; the earlier `benchmarkctl` command line was replaced by the `benching` hierarchy.
