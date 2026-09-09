# benching-dashboard

This dashboard is a read-only renderer for canonical artifacts produced by the `benching` repository.

- With `BENCHING_DATA_DIR` set, it reads `summary.json` from each immediate run subdirectory and `comparison-*.json` from that directory.
- Without `BENCHING_DATA_DIR`, it uses the checked-in `data/` fixtures.
- `lib/artifact-loader.ts` validates those artifacts before the UI consumes them.
- `lib/benchmark-data.ts` adapts canonical fields for display; it does not run benchmarks, parse raw logs, or recompute benchmark metrics.

For live artifacts, point the variable at `benching/runs` before starting the dashboard:

```powershell
$env:BENCHING_DATA_DIR = "C:\Users\Caleb\Downloads\Development\benching\runs"
npm run dev
```

To update the checked-in fixtures, copy canonical JSON artifacts into `data/`, then run `npm exec -- tsc --noEmit` and `npm run build`.

Provider colors and logos are presentation metadata only. Unknown providers render with a deterministic fallback color and no logo.
