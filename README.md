# Provider Benchmark

Reproducible Terminal-Bench 2.1 comparison of Kourier and ElectronHub Dev/Coding using OMP and the same canonical DeepSeek V4 Flash 0731 model.

## Fixed configuration

- Benchmark: Terminal-Bench 2.1, 89 tasks
- Agent: `agents.instrumented_omp_agent:InstrumentedOmpAgent`
- Canonical model: `deepseek-v4-flash-0731`
- Kourier API model: `DSV4-Flash-0731`
- ElectronHub Dev API model: `deepseek-v4-flash-0731:dev`
- Providers: `kourier`, `electronhub`
- Streaming: required
- Concurrency: 3
- Trials per task: 1
- Harbor retries: 0

The canonical benchmark model identifies the model being compared. `api_model` is the provider-facing identifier and may differ by provider.
Plan tiers are recorded explicitly in `config/providers.yaml` (Kourier: `omega`, ElectronHub: `Coding Plan (DevPass)`); observed capacity is never used to infer a plan tier.

## Setup

Install the project and ensure `docker`, `harbor`, and `omp` are available:

```bash
python3 -m pip install -e .
cp config/kourier.env.example config/kourier.env
cp config/electronhub.env.example config/electronhub.env
chmod 600 config/kourier.env config/electronhub.env
```

You only need a provider you intend to use. Copy the env file and set the API key for each provider you run; the others can be skipped. `harbor` and `omp` are internal CLI tools (see the org's setup docs); `harbor` must be on `PATH` and `omp` available inside the Harbor task image.

The analyzer uses the pinned official tokenizer repository `deepseek-ai/DeepSeek-V4-Flash-0731` at revision `7872f01b1d1fe23eabc4c98b48bffcef5a386062`. Prepare the cache once with `benchmarkctl prepare-tokenizer`; benchmark runs use `local_files_only=True` and never update it. `DEEPSEEK_V4_TOKENIZER` remains an optional local-cache override.

## Adding a provider

Add an entry to `config/providers.yaml` and a matching env file:

```yaml
providers:
  myprovider:
    enabled: true
    env_file: config/myprovider.env
    auth_env: MYPROVIDER_API_KEY
    base_url: https://api.myprovider.com/v1
    api_model: deepseek-v4-flash-0731
    api: openai-completions
    strict_model_check: false
    plan: null
    plan_tier: unknown
```

```bash
cp config/kourier.env.example config/myprovider.env
# set MYPROVIDER_API_KEY in config/myprovider.env
```

No code changes are needed; the provider is picked up automatically by `validate`, `smoke`, `full`, `probe-concurrency`, and `compare`. Set `strict_model_check: true` to require the `api_model` to appear in the provider's `/models` catalog during validation (ElectronHub does this).

## Commands

```bash
benchmarkctl prepare-tokenizer
benchmarkctl validate --provider kourier
benchmarkctl validate --provider electronhub
benchmarkctl probe-concurrency --provider kourier
benchmarkctl probe-concurrency --provider electronhub
benchmarkctl smoke --provider electronhub
benchmarkctl smoke --provider kourier
benchmarkctl full --provider kourier
benchmarkctl full --provider electronhub
benchmarkctl compare --providers kourier,electronhub --concurrency 3
```

Each command:

- `prepare-tokenizer` — downloads the pinned official DeepSeek tokenizer (`tokenizer.json`, config, etc.) into the local cache once, if not already present. Benchmark runs need it cached for exact local token counting; runs use the cache read-only and never re-download.
- `validate --provider <name>` — checks credentials and that the provider serves the configured model over streaming; the gatekeeper every run re-runs first.
- `probe-concurrency --provider <name> [--stages 2,3,5,6]` — stages direct concurrent-stream requests (default `2,3,5,6`) to find the provider's concurrency ceiling, stopping at the first rejected stage; doesn't touch benchmark scores.
- `smoke --provider <name>` — runs 3 quick Terminal-Bench tasks to confirm the full pipeline works.
- `full --provider <name>` — runs all 89 tasks; the real benchmark.
- `compare --providers <a>,<b>` — runs the given mode for one or more providers in parallel, then builds the comparison report. Works with a single provider too.

Validation is authoritative. Smoke and full runs refuse to start when provider preflight fails.

The probe stages 2, 3, 5, and one optional 6-stream test, stopping at the first rejected stage. It uses direct provider streaming requests, records 429/`Retry-After`, and never affects Terminal-Bench scores. Plan tiers come from `config/providers.yaml`; observed capacity never infers a tier.

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

Historical artifacts outside `runs/` are intentionally preserved and are not included in comparisons.

## Metric definitions

```text
TTFT = first_content_output - request_started
Decode duration = last_content_output - first_content_output
End-to-end latency = stream_completed - request_started
Decode TPS = locally counted output tokens / decode duration seconds
Effective TPS = locally counted output tokens / end-to-end latency seconds
CV = standard_deviation / mean
```

Provider-reported usage is stored separately from locally calculated output tokens. Local tokenization uses `tokenizers.Tokenizer` directly against `<tokenizer-cache>/tokenizer.json` with the pinned official cache. If the exact tokenizer is unavailable or output capture is truncated, local-token metrics are explicitly unavailable.

Cache metrics are never estimated. Missing provider cache fields remain unavailable.

## Architecture

```text
Terminal-Bench 2.1 -> Harbor -> OMP -> canonical proxy -> provider HTTPS API
                                               |
                                               +-> run-scoped raw.jsonl

analytics/analyze.py -> metrics.jsonl and comparison JSON
```
