# benching

Benchmark LLM API providers against terminal-agent task suites: run a task suite against one or more OpenAI-compatible providers behind a telemetry proxy, and compare latency, throughput, reliability, and task pass rates.

The repo keeps the default benchmark manifest in `config/benchmark.yaml`. User state, registered providers, credentials, and local benchmark manifests live under `~/.config/benching/` so normal CLI use does not rewrite the repository config.

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
config/benchmark.yaml      default benchmark suite identity
```

The CLI modules contain almost no benchmark logic: they parse arguments, call the `benchmark/` layer, and render results. A dashboard can import the same `benchmark/` functions.

## Requirements

- Python 3.12+, `docker`
- `harbor` and `omp` (see the org's setup docs); `harbor` must be on `PATH` and `omp` available inside the Harbor task image
- A provider serving an OpenAI-compatible streaming API

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

`config/benchmark.yaml` declares everything suite-specific:

```yaml
benchmark:
  name: my-suite
  version: "1.0"
  model: model-identifier            # optional benchmark default; /model overrides it
  reasoning: default                 # run default; /reasoning overrides it
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

The repository `config/benchmark.yaml` remains the fallback suite manifest.
Registered local suites overlay it when selected with `benching benchmark use`.

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
run.json                 immutable run configuration and fingerprint
status.json              lifecycle status
command.json             exact runner command
proxy-routes.json        trusted upstream routing configuration
raw.jsonl                proxy telemetry and captured debug data
metrics.jsonl            normalized analytical records
summary.json             stable dashboard-facing run summary
*.log                    runner and proxy logs
```

`benching runs` lists these; `benching results show` reads them. Run-id prefixes and `latest` resolve automatically.

Comparison artifacts under `runs/comparison-*.json` use schema version 1 and
contain benchmark identity, run IDs, selected models, execution mode,
tokenizer comparability, and embedded `summary.json` documents.

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
