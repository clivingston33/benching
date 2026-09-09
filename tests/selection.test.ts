import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import {
  createDataset,
  defaultSelection,
  getComparison,
  hasSelection,
  selectionLabel,
  type ArtifactDataset,
} from "@/lib/benchmark-data";
import { projectComparison, projectSummary } from "@/lib/contract";
import type { CanonicalComparison, CanonicalRunSummary } from "@/lib/canonical-types";

const fixtures = path.join(__dirname, "fixtures");

function readFixture(name: string): unknown {
  return JSON.parse(readFileSync(path.join(fixtures, name), "utf8"));
}

function dataset(): ArtifactDataset {
  const a = projectSummary(readFixture("summary-fireworks-a.json") as CanonicalRunSummary);
  const b = projectSummary(readFixture("summary-fireworks-b.json") as CanonicalRunSummary);
  const comparison = projectComparison(readFixture("comparison-fireworks-ab.json") as CanonicalComparison);
  return createDataset({ summary: a, summaries: [a, b], comparisons: [comparison], notices: [] });
}

test("stable comparison ids preferred over indices", () => {
  const data = dataset();
  const [option] = data.comparisonOptions;
  assert.equal(option.selection, "comparison:comparison-fireworks-ab");
  assert.equal(getComparison(data, option.selection).source.comparison_id, "comparison-fireworks-ab");
});

test("run_ids fallback resolves id-less comparisons", () => {
  const data = dataset();
  const legacy = { ...data.comparisons[0] };
  delete (legacy as Partial<CanonicalComparison>).comparison_id;
  const legacyDataset = createDataset({ summary: data.summary, summaries: data.summaries, comparisons: [legacy], notices: [] });
  const [option] = legacyDataset.comparisonOptions;
  assert.equal(option.selection, "comparison:bench-example-fireworks-a+bench-example-fireworks-b");
  assert.equal(getComparison(legacyDataset, option.selection).runs.length, 2);
});

test("legacy numeric index still resolves", () => {
  const data = dataset();
  assert.equal(getComparison(data, "comparison:0").source.comparison_id, "comparison-fireworks-ab");
});

test("unknown selection throws, missing selection falls back deterministically", () => {
  const data = dataset();
  assert.throws(() => getComparison(data, "comparison:nope"), /Unknown comparison selection/);
  assert.throws(() => getComparison(data, "run:nope"), /Unknown run selection/);
  assert.equal(hasSelection(data, "comparison:nope"), false);
  assert.equal(defaultSelection(data), "comparison:comparison-fireworks-ab");
  assert.match(selectionLabel(data, "comparison:nope"), /No artifact selected/);
});

test("empty dataset has a deterministic empty selection", () => {
  const data = createDataset({ summary: null, summaries: [], comparisons: [], notices: [] });
  assert.equal(defaultSelection(data), "");
  assert.equal(selectionLabel(data, ""), "No artifact selected");
});
