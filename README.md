# Provider Benchmark V1

Reproducible Terminal-Bench 2.1 comparison of Kourier and ElectronHub Dev/Coding using OMP and the same canonical DeepSeek V4 Flash 0731 model.

## Fixed configuration

- Benchmark: Terminal-Bench 2.1, 89 tasks
- Agent: `agents.instrumented_omp_agent:InstrumentedOmpAgent`
- Canonical model: `deepseek-v4-flash-0731`
- Kourier API model: `DSV4-Flash-0731`
- ElectronHub Dev API model: `deepseek-v4-flash-0731:dev`
- Providers: `kourier`, `electronhub`
- Streaming: required
- Reasoning: disabled
- Concurrency: 1
- Trials per task: 1
- Harbor retries: 0

The canonical benchmark model identifies the model being compared. `api_model` is the provider-facing identifier and may differ by provider.

## Setup

Install the project and ensure `docker`, `harbor`, and `omp` are available:

```bash
python3 -m pip install -e .
cp config/kourier.env.example config/kourier.env
cp config/electronhub.env.example config/electronhub.env
chmod 600 config/kourier.env config/electronhub.env
```

Provider credentials and endpoint overrides stay in the environment files. API model IDs are configured in `config/providers.yaml` after live discovery.

The analyzer uses the pinned official tokenizer repository `deepseek-ai/DeepSeek-V4-Flash-0731` at revision `7872f01b1d1fe23eabc4c98b48bffcef5a386062`. Prepare the cache once with `benchmarkctl prepare-tokenizer`; benchmark runs use `local_files_only=True` and never update it. `DEEPSEEK_V4_TOKENIZER` remains an optional local-cache override.

## Commands

```bash
benchmarkctl prepare-tokenizer
benchmarkctl validate --provider kourier
benchmarkctl validate --provider electronhub
benchmarkctl smoke --provider kourier
benchmarkctl smoke --provider electronhub
benchmarkctl full --provider kourier
benchmarkctl full --provider electronhub
benchmarkctl compare --providers kourier,electronhub
```

Validation is authoritative. Smoke and full runs refuse to start when provider preflight fails.

## Run artifacts

Each run is isolated under `runs/<run-id>/`:

```text
run.json                 immutable run configuration and fingerprint
status.json              lifecycle status
command.json             exact Harbor command
proxy-routes.json        trusted upstream routing configuration
raw.jsonl                proxy telemetry and captured debug data
metrics.jsonl            normalized analytical records
harbor/                  Harbor task artifacts
*.log                    Harbor and proxy logs
```

Historical artifacts outside `runs/` are intentionally preserved and are not included in V1 comparisons.

## Metric definitions

```text
TTFT = first_content_output - request_started
Decode duration = last_content_output - first_content_output
End-to-end latency = stream_completed - request_started
Decode TPS = locally counted output tokens / decode duration seconds
Effective TPS = locally counted output tokens / end-to-end latency seconds
CV = standard_deviation / mean
```

Provider-reported usage is stored separately from locally calculated output tokens. Local tokenization uses `transformers.AutoTokenizer` with `local_files_only=True` against the pinned official cache. If the exact tokenizer is unavailable or output capture is truncated, local-token metrics are explicitly unavailable.

Cache metrics are never estimated. Missing provider cache fields remain unavailable.

## Architecture

```text
Terminal-Bench 2.1 -> Harbor -> OMP -> canonical proxy -> provider HTTPS API
                                               |
                                               +-> run-scoped raw.jsonl

analytics/analyze.py -> metrics.jsonl and comparison JSON
```

The proxy forwards streams transparently, supports chunked/gzip responses, routes only to trusted controller-generated upstreams, and records task/trial correlation headers without forwarding them upstream. It records downstream cancellation separately from provider stream failure.

## Scope limits

V1 excludes synthetic inference benchmarks, other Terminal-Bench versions, SWE-bench, pricing, dashboards, CSV/HTML reporting, cache estimation, reasoning-model support, and concurrency load testing.
