# Release acceptance (alpha)

This milestone defines release **gates**, not release publishing. Nothing
is uploaded to PyPI or npm here; tags only mark reviewed commits.

## Versions are independent

```text
benching            Python package version (pyproject.toml)
benching-dashboard  dashboard version (dashboard/package.json, private)
schema_version      canonical artifact major version (schemas/)
metric_revision     analyzer metric-definition revision
```

Never lock them together. A dashboard-only change must not force a Python
version bump, and vice versa.

## Tag convention

```text
benching-vX.Y.Z    Python engine/CLI release
dashboard-vX.Y.Z   dashboard deployment release
```

Do not bump versions as part of feature PRs; maintainers tag when the
checklist below is fully green.

## Alpha acceptance checklist

Every box must hold before tagging. Each maps to an executable gate.

```text
[ ] GitHub CI fully green on the tagged commit
[ ] Python full suite green (`python -m pytest -q` from an editable install)
[ ] Dashboard tests green (`npm test` from dashboard/)
[ ] TypeScript green (`npm exec -- tsc --noEmit --incremental false`)
[ ] Next production build green (`npm run build`)
[ ] wheel + sdist build (`python -m build`, both artifacts present)
[ ] Fresh wheel install smoke outside the checkout:
    benching --help, doctor, runs, results --help, tokenizer --help,
    plus packaged default YAML and schema loading
[ ] Contract examples validate on both sides (contracts workflow)
[ ] Release hygiene green (LICENSE present, metadata consistent, public
    fixtures clean, distributions contain no private files, dashboard
    bundle carries no test markers)
[ ] LICENSE/provenance review clean (THIRD_PARTY_NOTICES.md current)
[ ] No BLOCKER/HIGH known release issue open against the tagged scope
```

## Recommended required branch-protection checks

Configure these exact check names as required (do not claim protection is
on until someone with admin access enables it):

```text
tests (py3.12, ubuntu-latest)
tests (py3.13, ubuntu-latest)
tests (py3.12, windows-latest)
wheel/sdist build and fresh-install smoke
license/provenance/package hygiene
install, test, typecheck, production build
producer and consumer compatibility
```

## Release scope (non-publishing)

CI builds release artifacts for validation only. If a future workflow
uploads artifacts on tags, it must remain non-publishing (no PyPI/npm
upload) until a later milestone explicitly justifies and tests it.
