// Syncs contract inputs from the sibling benching checkout.
//
// The benching repo owns the authoritative schemas and example artifacts.
// This script copies them here so the dashboard builds and tests against
// the real producer contract while the repos remain separate. Do not
// hand-edit the outputs; M3 monorepo migration removes this mechanism.
// Usage: node scripts/sync-contract.mjs [--check]
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dashboard = path.resolve(here, "..");
const benching = path.resolve(dashboard, "..", "benching");

const pairs = [
  ["src/benching/benchmark/schemas/summary-v1.schema.json", "schemas/summary-v1.schema.json"],
  ["src/benching/benchmark/schemas/comparison-v1.schema.json", "schemas/comparison-v1.schema.json"],
  ["examples/artifacts/summary-fireworks-a.json", "tests/fixtures/summary-fireworks-a.json"],
  ["examples/artifacts/summary-fireworks-b.json", "tests/fixtures/summary-fireworks-b.json"],
  ["examples/artifacts/comparison-fireworks-ab.json", "tests/fixtures/comparison-fireworks-ab.json"],
];

const check = process.argv.includes("--check");
let failed = false;
for (const [from, to] of pairs) {
  const source = path.join(benching, from);
  const target = path.join(dashboard, to);
  if (!existsSync(source)) {
    console.log(`skip (no benching checkout): ${from}`);
    continue;
  }
  if (check) {
    if (!existsSync(target) || readFileSync(source, "utf8") !== readFileSync(target, "utf8")) {
      console.error(`drift: ${to} differs from ${from}; run node scripts/sync-contract.mjs`);
      failed = true;
    }
    continue;
  }
  mkdirSync(path.dirname(target), { recursive: true });
  copyFileSync(source, target);
  console.log(`synced ${to}`);
}
process.exit(failed ? 1 : 0);
