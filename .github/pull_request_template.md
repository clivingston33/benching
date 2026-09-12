## What changed?

## Why?

## What tests were run?

```text
Python:   python -m pytest -q
Dashboard: npm test + tsc + next build (from dashboard/)
Packaging: python -m build (if applicable)
```

## Does this change artifact/schema semantics?

If yes: producer and dashboard compatibility updates must be in this PR,
and `examples/artifacts/` regeneration must be reviewed field by field.

## Checklist

- [ ] Focused scope, no drive-by refactors
- [ ] No secrets, `.env` files, `runs/` output, or raw telemetry committed
- [ ] CI passes (or failures explained)
