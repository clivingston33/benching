import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import {
  comparisonIdentityErrors,
  comparisonSchemaErrors,
  projectComparison,
  projectSummary,
  summarySchemaErrors,
} from "@/lib/contract";
import type { CanonicalComparison, CanonicalRunSummary } from "@/lib/canonical-types";

const root = path.join(__dirname, "..");
const schemasDir = path.join(root, "schemas");
const fixtures = path.join(__dirname, "fixtures");
const benching = path.resolve(root, "..", "benching");

function readJson(file: string): unknown {
  return JSON.parse(readFileSync(file, "utf8"));
}

test("synced schemas match the authoritative producer source", () => {
  for (const name of ["summary-v1.schema.json", "comparison-v1.schema.json"]) {
    const source = path.join(benching, "src", "benching", "benchmark", "schemas", name);
    if (!existsSync(source)) {
      console.log(`skip: no benching checkout at ${source}`);
      continue;
    }
    assert.equal(
      readFileSync(path.join(schemasDir, name), "utf8"),
      readFileSync(source, "utf8"),
      `${name} drifted from benching/src/benching/benchmark/schemas`
    );
  }
});

test("synced example fixtures match the producer corpus", () => {
  for (const name of ["summary-fireworks-a.json", "summary-fireworks-b.json", "comparison-fireworks-ab.json"]) {
    const source = path.join(benching, "examples", "artifacts", name);
    if (!existsSync(source)) {
      console.log(`skip: no benching checkout at ${source}`);
      continue;
    }
    assert.equal(readFileSync(path.join(fixtures, name), "utf8"), readFileSync(source, "utf8"), `${name} drifted`);
  }
});

test("valid corpus passes schema validation", () => {
  for (const name of ["summary-fireworks-a.json", "summary-fireworks-b.json"]) {
    assert.deepEqual(summarySchemaErrors(readJson(path.join(fixtures, name))), []);
  }
  assert.deepEqual(comparisonSchemaErrors(readJson(path.join(fixtures, "comparison-fireworks-ab.json"))), []);
});

test("malformed nested metric fails with a concise diagnostic", () => {
  const errors = summarySchemaErrors(readJson(path.join(fixtures, "summary-malformed.json")));
  assert.equal(errors.length, 1);
  assert.match(errors[0], /decode_tps/);
  assert.ok(errors[0].length < 300, "diagnostic stays concise");
});

test("embedded identity mismatch is caught", () => {
  const comparison = readJson(path.join(fixtures, "comparison-fireworks-ab.json")) as CanonicalComparison;
  assert.deepEqual(comparisonIdentityErrors(comparison), []);
  const broken = { ...comparison, run_ids: [...comparison.run_ids, "bench-ghost"] };
  assert.deepEqual(comparisonIdentityErrors(broken).length, 1);
});

test("projection strips unknown fields and stays schema-valid", () => {
  const raw = readJson(path.join(fixtures, "summary-fireworks-a.json")) as Record<string, unknown>;
  raw.private_secret = "DO_NOT_EXPOSE";
  (raw.tokens as Record<string, unknown>).evil = "DO_NOT_EXPOSE";
  const projected = projectSummary(raw as unknown as CanonicalRunSummary);
  assert.ok(!JSON.stringify(projected).includes("DO_NOT_EXPOSE"));
  assert.deepEqual(summarySchemaErrors(projected), []);
  const rawComparison = readJson(path.join(fixtures, "comparison-fireworks-ab.json")) as Record<string, unknown>;
  rawComparison.private_secret = "DO_NOT_EXPOSE";
  const projectedComparison = projectComparison(rawComparison as unknown as CanonicalComparison);
  assert.ok(!JSON.stringify(projectedComparison).includes("DO_NOT_EXPOSE"));
  assert.deepEqual(comparisonSchemaErrors(projectedComparison), []);
  assert.deepEqual(comparisonIdentityErrors(projectedComparison), []);
});

test("projection preserves provenance and new optional fields", () => {
  const projected = projectSummary(readFixtureSummaryA());
  assert.equal(projected.metric_revision, 2);
  assert.deepEqual(projected.tokenizer, { repo: "org/example-tok", revision: "rev-1", available: true });
  const comparison = projectComparison(readFixtureComparison());
  assert.equal(comparison.comparison_id, "comparison-fireworks-ab");
  assert.equal(comparison.tokenizer_identity_status, "known_equal");
});

function readFixtureSummaryA(): CanonicalRunSummary {
  return readJson(path.join(fixtures, "summary-fireworks-a.json")) as CanonicalRunSummary;
}

function readFixtureComparison(): CanonicalComparison {
  return readJson(path.join(fixtures, "comparison-fireworks-ab.json")) as CanonicalComparison;
}
