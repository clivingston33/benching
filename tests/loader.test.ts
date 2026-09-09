import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { loadArtifactsFromDirectory } from "@/lib/artifact-loader";

const fixtures = path.join(__dirname, "fixtures");

function readFixture(name: string): unknown {
  return JSON.parse(readFileSync(path.join(fixtures, name), "utf8"));
}

function writeRun(dir: string, name: string, summary: unknown): void {
  const runDir = path.join(dir, name);
  mkdirSync(runDir, { recursive: true });
  writeFileSync(path.join(runDir, "summary.json"), JSON.stringify(summary));
}

test("valid corpus loads with no notices", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  writeRun(dir, "run-a", readFixture("summary-fireworks-a.json"));
  writeRun(dir, "run-b", readFixture("summary-fireworks-b.json"));
  writeFileSync(path.join(dir, "comparison-fireworks-ab.json"), JSON.stringify(readFixture("comparison-fireworks-ab.json")));
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 2);
  assert.equal(artifacts.comparisons.length, 1);
  assert.deepEqual(artifacts.notices, []);
  assert.ok(artifacts.summary);
});

test("malformed nested metric is invalid, valid runs still render", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  writeRun(dir, "run-a", readFixture("summary-fireworks-a.json"));
  writeRun(dir, "run-bad", readFixture("summary-malformed.json"));
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 1);
  assert.equal(artifacts.summaries[0].run_id, "bench-example-fireworks-a");
  assert.equal(artifacts.notices.length, 1);
  assert.equal(artifacts.notices[0].kind, "invalid");
  assert.match(artifacts.notices[0].reason, /decode_tps/);
});

test("missing required field and wrong type are invalid", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  const missing = readFixture("summary-fireworks-a.json") as Record<string, unknown>;
  delete missing.run_id;
  writeRun(dir, "run-a", missing);
  const wrongType = readFixture("summary-fireworks-b.json") as Record<string, unknown>;
  (wrongType as Record<string, unknown>).tasks = "nope";
  writeRun(dir, "run-b", wrongType);
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 0);
  assert.equal(artifacts.notices.length, 2);
  assert.ok(artifacts.notices.every((notice) => notice.kind === "invalid"));
});

test("future major version is unsupported, not malformed", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  writeRun(dir, "run-a", readFixture("summary-fireworks-a.json"));
  writeFileSync(path.join(dir, "comparison-v2.json"), JSON.stringify(readFixture("comparison-v2.json")));
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 1);
  assert.equal(artifacts.comparisons.length, 0);
  assert.equal(artifacts.notices.length, 1);
  assert.equal(artifacts.notices[0].kind, "unsupported_version");
  assert.match(artifacts.notices[0].reason, /schema version 2/);
});

test("embedded run id mismatch invalidates only that comparison", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  writeRun(dir, "run-a", readFixture("summary-fireworks-a.json"));
  const comparison = readFixture("comparison-fireworks-ab.json") as { run_ids: string[] };
  comparison.run_ids = ["bench-example-fireworks-a", "bench-example-fireworks-ZZZ"];
  writeFileSync(path.join(dir, "comparison-broken.json"), JSON.stringify(comparison));
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 1);
  assert.equal(artifacts.comparisons.length, 0);
  assert.equal(artifacts.notices.length, 1);
  assert.match(artifacts.notices[0].reason, /run_ids/);
});

test("unknown private fields are stripped before adapters", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  const sneaky = JSON.parse(JSON.stringify(readFixture("summary-fireworks-a.json"))) as Record<string, unknown>;
  sneaky.private_secret = "DO_NOT_EXPOSE";
  (sneaky.tokens as Record<string, unknown>).evil = "DO_NOT_EXPOSE";
  (sneaky.tasks as Array<Record<string, unknown>>)[0].notes = "DO_NOT_EXPOSE";
  writeRun(dir, "run-a", sneaky);
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 1);
  assert.equal(artifacts.notices.length, 0);
  assert.ok(!JSON.stringify(artifacts.summaries[0]).includes("DO_NOT_EXPOSE"));
});

test("empty directory yields an empty state, not a crash", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 0);
  assert.equal(artifacts.comparisons.length, 0);
  assert.equal(artifacts.summary, null);
});

test("missing directory yields an unreadable notice, not a crash", () => {
  const artifacts = loadArtifactsFromDirectory(path.join(tmpdir(), "benching-does-not-exist-xyz"));
  assert.equal(artifacts.summaries.length, 0);
  assert.equal(artifacts.notices.length, 1);
  assert.equal(artifacts.notices[0].kind, "unreadable");
});

test("unreadable artifact file is surfaced without crashing siblings", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "benching-"));
  writeRun(dir, "run-a", readFixture("summary-fireworks-a.json"));
  writeFileSync(path.join(dir, "comparison-broken.json"), "{oops");
  const artifacts = loadArtifactsFromDirectory(dir);
  assert.equal(artifacts.summaries.length, 1);
  assert.equal(artifacts.comparisons.length, 0);
  assert.equal(artifacts.notices.length, 1);
  assert.equal(artifacts.notices[0].kind, "invalid");
});
