# Publication policy: what may leave this machine

## Safe to publish / share

- Canonical `summary.json` (validated against `summary-v1.schema.json`).
- Canonical `comparison-*.json` (validated against
  `comparison-v1.schema.json`).
- Intentionally sanitized snapshots under `examples/artifacts/`
  (see `examples/README.md` for provenance; regenerated and compared by
  `tests/test_contract.py::test_examples_match_producer`).
- The dashboard's curated demo data under `dashboard/data/`
  (synthetic fixture content, no private fields).

"Public artifact" means *designed for publication*. It does not mean
"non-sensitive under every future custom benchmark": provider/model/suite
identifiers and task labels are user-supplied strings. If your benchmark
identifiers, model names, or provider names are themselves confidential,
treat even canonical summaries as private.

## Private by default — never publish, attach to issues, or commit

- `raw.jsonl` — full prompts, histories, and unredacted model output.
- `metrics.jsonl` — per-request detail including error/routing metadata.
- `run.json` — private execution metadata (endpoint, settings, fingerprint).
- `status.json` details when environment-specific (PIDs, host paths).
- `command.json` — full Harbor argv (may carry the run's proxy auth token
  redacted on disk, but still internal).
- `proxy-auth.json` — the run-scoped proxy credential.
- Provider credential files (`*.env` under the providers directory) and
  any `auth_env`-referenced secrets.
- `*.log` files, Harbor task workspaces (`runs/<id>/harbor/`), and
  `proxy-routes.json`.
- Any `.env` file that is not an `.example` template.

The dashboard projection (`dashboard/lib/contract.ts`) allowlists public
fields and drops unknown/private extras; schema validation must not be
confused with sanitization. Raw diagnostics stay server-side / local-only.

## File permissions

Credential-bearing files are created with restrictive permissions on POSIX
(`0600`; see `benchmark/security.py::write_credential_file`). Restrictive
modes are best-effort on Windows, where ACL semantics differ — prefer the
native credential store or an ephemeral checkout on shared Windows hosts.

## If you suspect a secret was committed

Do not file a public issue with the value. Contact the maintainer
privately (see the commit history for the current contact address),
rotate the credential immediately, and assume any pushed history is
compromised until the rotation is confirmed. History rewrites are
evaluated case by case, never automatic.

## Hygiene gates

`tests/test_release_hygiene.py` scans committed public examples/fixtures
for key material, home-directory paths, and private-artifact fields, and
verifies packaging/ignore boundaries. The dashboard contract suite proves
projection strips unknown/private fields (`DO_NOT_EXPOSE` markers).
