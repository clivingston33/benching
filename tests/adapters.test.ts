import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import {
  breakdownRowsFor,
  comparisonRowsFor,
  contextRowsFor,
  createDataset,
  getComparison,
  metricRowsFor,
  runDisplayLabel,
  seriesFor,
  taskResultsFor,
  tokenRowsFor,
  type ArtifactDataset,
  type RunSelection,
} from "@/lib/benchmark-data";
import { projectComparison, projectSummary } from "@/lib/contract";
import type { CanonicalComparison, CanonicalRunSummary } from "@/lib/canonical-types";

const fixtures = path.join(__dirname, "fixtures");

function readFixture(name: string): unknown {
  return JSON.parse(readFileSync(path.join(fixtures, name), "utf8"));
}

function corpus(): { a: CanonicalRunSummary; b: CanonicalRunSummary; comparison: CanonicalComparison } {
  const a = projectSummary(readFixture("summary-fireworks-a.json") as CanonicalRunSummary);
  const b = projectSummary(readFixture("summary-fireworks-b.json") as CanonicalRunSummary);
  const comparison = projectComparison(readFixture("comparison-fireworks-ab.json") as CanonicalComparison);
  return { a, b, comparison };
}

function datasetFor(selection: RunSelection, runs: CanonicalRunSummary[], comparisons: CanonicalComparison[]): { dataset: ArtifactDataset; selection: RunSelection } {
  const dataset = createDataset({ summary: runs[0] ?? null, summaries: runs, comparisons, notices: [] });
  return { dataset, selection };
}

test("same-provider runs stay distinct everywhere (10 vs 90)", () => {
  const { a, b, comparison } = corpus();
  const { dataset, selection } = datasetFor(`comparison:${comparison.comparison_id}`, [a, b], [comparison]);
  const speed = comparisonRowsFor(dataset, selection).find((row) => row.metric === "Median Output Speed");
  assert.deepEqual(speed?.values, { [a.run_id]: "10 tok/s", [b.run_id]: "90 tok/s" });
  const metrics = metricRowsFor(dataset, selection, "decode_tps") as unknown as Array<Record<string, number | null>>;
  assert.deepEqual([metrics[0][a.run_id], metrics[0][b.run_id]], [10, 90]);
  const context = contextRowsFor(dataset, selection, "speed").find((row) => row.label === "0-4K") as unknown as Record<string, number | null> | undefined;
  assert.deepEqual([context?.[a.run_id], context?.[b.run_id]], [10, 90]);
  const tasks = taskResultsFor(dataset, selection).find((task) => task.taskId === "task-a");
  assert.ok(tasks?.results[a.run_id] && tasks?.results[b.run_id]);
  assert.notEqual(tasks?.results[a.run_id], tasks?.results[b.run_id]);
  assert.equal(tasks?.results[a.run_id]?.passed, true);
  assert.equal(tasks?.results[b.run_id]?.passed, true);
  const tokens = tokenRowsFor(dataset, selection);
  assert.equal(tokens.length, 2);
  assert.notEqual(tokens[0].provider, tokens[1].provider);
  const breakdown = breakdownRowsFor(dataset, selection);
  assert.ok(`${a.run_id}-timeout` in breakdown[0]);
  assert.ok(`${b.run_id}-timeout` in breakdown[1]);
});

test("same-provider same-model runs stay distinct", () => {
  const { a, b, comparison } = corpus();
  const c = { ...b, run_id: "bench-example-fireworks-c", model: a.model };
  const sameModel = { ...comparison, runs: [a, c] };
  const { dataset, selection } = datasetFor(`comparison:${comparison.comparison_id}`, [a, c], [sameModel]);
  const speed = comparisonRowsFor(dataset, selection).find((row) => row.metric === "Median Output Speed");
  assert.deepEqual(speed?.values, { [a.run_id]: "10 tok/s", [c.run_id]: "90 tok/s" });
  assert.notEqual(runDisplayLabel(a, [a, c]), runDisplayLabel(c, [a, c]));
});

test("display labels disambiguate repeats, stay simple otherwise", () => {
  const { a, b } = corpus();
  assert.equal(runDisplayLabel(a, [a, b]), "Fireworks · deepseek-v4");
  const c = { ...b, run_id: "bench-example-fireworks-c", model: a.model };
  assert.notEqual(runDisplayLabel(a, [a, c]), runDisplayLabel(c, [a, c]));
  assert.match(runDisplayLabel(c, [a, c]), /Fireworks · deepseek-v4 · /);
});

test("series keys are run ids with provider presentation metadata", () => {
  const { a, b } = corpus();
  const series = seriesFor([a, b]);
  assert.deepEqual(series.map((item) => item.key), [a.run_id, b.run_id]);
  assert.equal(series[0].name, "Fireworks");
  assert.ok(series[0].color);
});

test("task results group by task+trial with run-scoped slots", () => {
  const { a, b, comparison } = corpus();
  const { dataset, selection } = datasetFor(`comparison:${comparison.comparison_id}`, [a, b], [comparison]);
  for (const group of taskResultsFor(dataset, selection)) {
    assert.deepEqual(Object.keys(group.results).sort(), [a.run_id, b.run_id].sort());
  }
});

test("unknown trial renders without crashing adapters", () => {
  const { a, comparison } = corpus();
  const missing = { ...a, tasks: [{ ...a.tasks[0], trial_id: null as string | null, passed: null, reward: null, requests: 0 }] };
  const { dataset, selection } = datasetFor(`comparison:${comparison.comparison_id}`, [missing], [{ ...comparison, runs: [missing] }]);
  const groups = taskResultsFor(dataset, selection);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].trialId, null);
});
