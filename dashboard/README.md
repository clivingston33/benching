# Benching dashboard

This dashboard lives at `dashboard/` in the `benching` monorepo. It is a
read-only renderer for canonical artifacts produced by the Python CLI. It
builds and deploys independently: `npm ci`, `npm test`, `npm run build`
from this directory, with no Python runtime required.

- With `BENCHING_DATA_DIR` set, it reads `summary.json` from each immediate run subdirectory and `comparison-*.json` from that directory.
- Without `BENCHING_DATA_DIR`, it uses the checked-in `data/` fixtures.
- `lib/artifact-loader.ts` validates those artifacts before the UI consumes them.
- `lib/benchmark-data.ts` adapts canonical fields for display; it does not run benchmarks, parse raw logs, or recompute benchmark metrics.
- Schemas are the single physical source at `../src/benching/benchmark/schemas/`, bundled at build time. Never crawl `../runs`; point the variable at an explicitly curated public artifact directory.
- Container builds (if added) should use `dashboard/` as the build context; only the JSON schemas/examples are read from the repository root at build time, never at runtime.

```powershell
$env:BENCHING_DATA_DIR = "C:\curated\benching-artifacts"
npm run dev
```

To update the checked-in fixtures, copy canonical JSON artifacts into `data/`, then run `npm exec -- tsc --noEmit` and `npm run build`.

Provider colors and logos are presentation metadata only. Unknown providers render with a deterministic fallback color and no logo.
