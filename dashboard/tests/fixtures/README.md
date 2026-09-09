# Dashboard contract test fixtures

`summary-fireworks-a.json`, `summary-fireworks-b.json`, and
`comparison-fireworks-ab.json` are synchronized copies of
`benching/examples/artifacts/` (authoritative producer output: same
provider, distinct runs, decode p50 10 vs 90 tok/s). Do not hand-edit;
run `npm run contract:sync` (M3 monorepo migration removes this step).

The remaining fixtures are handwritten edge cases:

- `summary-malformed.json`: valid summary with `"speed": {}` (audit H4
  reproduction: must be rejected before rendering, never crash it).
- `comparison-v2.json`: well-formed comparison with `schema_version: 2`
  (must classify as unsupported, not malformed).
- `summary-identity-mismatch.json`: not a file; the embedded-identity
  mismatch case is built programmatically in `loader.test.ts`.
- `summary-private.json`: built programmatically (valid summary plus a
  synthetic `private_secret` field) to prove projection strips it.
