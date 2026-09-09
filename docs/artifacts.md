# Artifact contract

## Boundaries

```text
PUBLIC (dashboard-safe)
  summary.json            canonical portable per-run result
  comparison-*.json       portable comparison with embedded summaries

PRIVATE (never mounted/published to the dashboard)
  run.json                execution provenance (endpoints, paths, settings)
  status.json             lifecycle state (internal)
  raw.jsonl               sensitive transport telemetry (prompts, output)
  metrics.jsonl           detailed per-request analysis output
  command.json            runner argv (proxy token redacted at rest)
  proxy-routes.json       upstream routing configuration
  proxy-auth.json         run-scoped proxy credential (0600)
  *.log / harbor/         execution logs and task environments
  <provider>.env          API credentials (0600)
```

Authoritative JSON Schemas live in `benchmark/schemas/` (`summary-v1.schema.json`,
`comparison-v1.schema.json`, draft 2020-12). Consumers validate before use
and project only schema-defined public fields; unknown extras are accepted
by validation (additive evolution) but stripped before browser
serialization, never rendered blindly.

## Versioning

`schema_version: 1` is a compatibility boundary. Consumers accept major 1
and report any other major as unsupported (never parse it as v1, never
crash the collection over it). Additive optional fields do not change the
major. `metric_revision` (currently 2) tracks canonical metric-definition
changes independently of shape: explicit stream completion, semantic output
counting, independent per-run normalization, planned task accounting.

## Units and nulls

Latency fields are milliseconds, throughput fields tokens per second, rates
are fractions in [0, 1] (overlapping categories such as timeout, HTTP
error, and failure rates are independent and must never be constrained to
sum to 100%). Counts are nonnegative integers. Null means unavailable or
unknown — never zero, never estimated.

## Tokenizer availability

`summary.tokenizer` carries the pinned `{repo, revision}` identity plus
`available` (local counting actually possible for this run). Two missing
identities are unknown, never proven equal; see `tokenizer_identity_status`
(`known_equal` / `known_different` / `unknown`) on comparisons alongside the
`tokenizers_comparable` boolean.

## Tasks, trials, rewards

Task entries are keyed by `(task_id, trial_id)`; `trial_id` may be null.
Planned-but-unobserved work appears with `requests: 0` and null verdict
fields: explicit absence, never a fabricated failure. Numeric verifier
`reward` is preserved exactly; `passed` is the derived binary convenience
(`reward == 1.0`) for the current binary suite and must not replace it.

## Context buckets

Provider input-token half-open buckets (`[0,4K)`, `[4K,16K)`, …) plus an
explicit `unknown` bucket with the same shape. Bucketed plus unknown always
equals the analyzed request population; unknown input is never assigned to
a zero-token bucket.

## Comparisons

Comparisons embed the independent run summaries (`run_ids` must match the
embedded ids) with suite/model/execution compatibility metadata.
`comparison_id` is the stable document identity (filename stem).
`official_comparison` marks the sequential execution protocol, not an
endorsement of fairness. Comparisons never rewrite their inputs.

## Support promise

Currently generated artifacts plus the retained v1 fixtures
(`tests/fixtures/summary.json`, the dashboard demo corpus, and
`examples/artifacts/`) validate under these schemas. Additive optional
fields stay valid for old readers; removing fields, changing units, or
changing requiredness needs a new major schema.
