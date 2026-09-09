# Dashboard contract test fixtures

Valid artifacts are read directly from the authoritative producer corpus
at `examples/artifacts/` (same provider, distinct runs, decode p50 10 vs
90 tok/s). There are no synchronized copies: `lib/contract.ts` likewise
imports the producer-owned schemas at
`src/benching/benchmark/schemas/` with no duplicate.

Only dashboard-specific edge cases live here:

- `summary-malformed.json`: valid summary with `"speed": {}` (audit H4
  reproduction: must be rejected before rendering, never crash it).
- `comparison-v2.json`: well-formed comparison with `schema_version: 2`
  (must classify as unsupported, not malformed).
- `summary-identity-mismatch.json`: not a file; the embedded-identity
  mismatch case is built programmatically in `loader.test.ts`.
- `summary-private.json`: built programmatically (valid summary plus a
  synthetic `private_secret` field) to prove projection strips it.
