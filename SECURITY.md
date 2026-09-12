# Security policy

Benching is pre-1.0. Security fixes are provided for the **latest
released alpha/minor line only**. There are no long-term support branches;
upgrade to the newest tag.

## Reporting a vulnerability

**Do not open a public GitHub issue for suspected vulnerabilities or
leaked credentials.** Either:

- use GitHub private vulnerability reporting on this repository, if
  enabled, or
- email the maintainer privately at `caleb.livingston33@gmail.com`
  (the address already public in the repository's commit history).

Include: affected component and version/tag, what you observed, and steps
to reproduce that avoid live provider credentials. Expect an initial
response within a few days; this is a spare-time project.

## What not to put in public issues

- provider API keys or proxy auth tokens
- `.env` contents or credential-file paths with secrets
- `raw.jsonl`, `metrics.jsonl`, `run.json`, logs, or Harbor workspaces
- prompts or model output from non-public benchmarks

Share only canonical `summary.json` / `comparison-*.json` (see
`docs/publication.md` for the full public/private list).

## If you leaked a credential

Rotate it immediately at the provider, then notify the maintainer so any
mirrored history can be assessed. Assume pushed history is compromised
until rotation is confirmed. History rewrites are case-by-case, never
automatic.

## Scope of particular concern

```text
provider credential storage and registry validation
proxy per-run authentication and readiness identity
run-directory path containment
canonical artifact privacy (projection of unknown/private fields)
owned-process cleanup (no unrelated container/process interference)
dashboard exposure of private run data
dependency or installer supply chain (pinned OMP binary, lockfiles)
```
