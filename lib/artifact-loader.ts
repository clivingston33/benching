import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import summaryArtifact from "@/data/summary.json";
import comparisonJanuary from "@/data/comparison-20260102.json";
import { isCanonicalObject, type CanonicalComparison, type CanonicalRunSummary } from "@/lib/canonical-types";

function requiredRecord(value: Record<string, unknown>, key: string, source: string): Record<string, unknown> {
  const child = value[key];
  if (!isCanonicalObject(child)) throw new Error(`${source}: missing object "${key}"`);
  return child;
}

function nullableNumber(value: unknown): boolean {
  return value === null || typeof value === "number";
}

function validateContextMetric(value: unknown, source: string, percentiles: boolean): void {
  if (!isCanonicalObject(value) || !nullableNumber(value.mean)) throw new Error(`${source}: malformed metric`);
  if (percentiles && (!nullableNumber(value.p50) || !nullableNumber(value.p95))) throw new Error(`${source}: malformed metric percentiles`);
}

function validateTask(value: unknown, source: string): void {
  if (!isCanonicalObject(value)) throw new Error(`${source}: expected an object`);
  if (typeof value.task_id !== "string" || (value.trial_id !== null && typeof value.trial_id !== "string")) throw new Error(`${source}: malformed task identity`);
  if (value.passed !== null && typeof value.passed !== "boolean") throw new Error(`${source}: malformed passed`);
  for (const key of ["reward", "duration_sec"]) if (!nullableNumber(value[key])) throw new Error(`${source}: malformed ${key}`);
  if (value.exception !== null && typeof value.exception !== "string") throw new Error(`${source}: malformed exception`);
  if (value.timeout !== null && typeof value.timeout !== "boolean") throw new Error(`${source}: malformed timeout`);
  if (typeof value.requests !== "number") throw new Error(`${source}: malformed requests`);
  const tokens = requiredRecord(value, "tokens", source);
  for (const key of ["input", "output", "cache_read", "cache_write"]) if (!nullableNumber(tokens[key])) throw new Error(`${source}: malformed tokens.${key}`);
  const latency = requiredRecord(value, "latency", source);
  for (const key of ["ttft_ms_mean", "ttft_ms_p50", "ttft_ms_p95", "end_to_end_latency_ms_mean"]) if (!nullableNumber(latency[key])) throw new Error(`${source}: malformed latency.${key}`);
  const reliability = requiredRecord(value, "reliability", source);
  if (typeof reliability.successful_requests !== "number" || typeof reliability.failed_requests !== "number" || !nullableNumber(reliability.success_rate)) throw new Error(`${source}: malformed reliability`);
}

function validateRun(value: unknown, source: string): CanonicalRunSummary {
  if (!isCanonicalObject(value)) throw new Error(`${source}: expected an object`);
  if (value.schema_version !== 1) throw new Error(`${source}: unsupported schema_version ${String(value.schema_version)}`);
  if (typeof value.run_id !== "string" || !value.run_id) throw new Error(`${source}: missing run_id`);
  if (typeof value.created_at_utc !== "string") throw new Error(`${source}: missing created_at_utc`);
  const benchmark = requiredRecord(value, "benchmark", source);
  if (typeof benchmark.name !== "string" || typeof benchmark.version !== "string" || typeof benchmark.task_count !== "number") throw new Error(`${source}: malformed benchmark`);
  const provider = requiredRecord(value, "provider", source);
  if (typeof provider.id !== "string" || typeof provider.name !== "string") throw new Error(`${source}: malformed provider`);
  if (typeof value.model !== "string") throw new Error(`${source}: missing model`);
  if (value.reasoning !== "default" && value.reasoning !== "enabled" && value.reasoning !== "disabled") throw new Error(`${source}: malformed reasoning`);
  const execution = requiredRecord(value, "execution", source);
  if (typeof execution.concurrency !== "number" || typeof execution.trials !== "number") throw new Error(`${source}: malformed execution`);
  for (const key of ["score", "speed", "latency", "reliability", "tokens"]) requiredRecord(value, key, source);
  const context = requiredRecord(value, "context", source);
  for (const [bucketName, bucketValue] of Object.entries(context)) {
    const bucket = isCanonicalObject(bucketValue) ? bucketValue : null;
    if (!bucket || typeof bucket.requests !== "number" || !nullableNumber(bucket.failure_rate)) throw new Error(`${source}.context.${bucketName}: malformed bucket`);
    validateContextMetric(bucket.ttft_ms, `${source}.context.${bucketName}.ttft_ms`, true);
    validateContextMetric(bucket.decode_tps, `${source}.context.${bucketName}.decode_tps`, true);
    validateContextMetric(bucket.end_to_end_latency_ms, `${source}.context.${bucketName}.end_to_end_latency_ms`, false);
  }
  if (!Array.isArray(value.tasks)) throw new Error(`${source}: tasks must be an array`);
  value.tasks.forEach((task, index) => validateTask(task, `${source}.tasks[${index}]`));
  return value as unknown as CanonicalRunSummary;
}

function validateComparison(value: unknown, source: string): CanonicalComparison {
  if (!isCanonicalObject(value)) throw new Error(`${source}: expected an object`);
  if (value.schema_version !== 1) throw new Error(`${source}: unsupported schema_version ${String(value.schema_version)}`);
  const benchmark = requiredRecord(value, "benchmark", source);
  if (typeof benchmark.name !== "string" || typeof benchmark.version !== "string") throw new Error(`${source}: malformed benchmark`);
  if (!Array.isArray(value.run_ids) || !Array.isArray(value.models)) throw new Error(`${source}: missing run_ids or models`);
  if (value.execution_mode !== "sequential" && value.execution_mode !== "parallel") throw new Error(`${source}: malformed execution_mode`);
  if (typeof value.official_comparison !== "boolean" || typeof value.tokenizers_comparable !== "boolean") throw new Error(`${source}: malformed comparison flags`);
  if (!Array.isArray(value.runs) || value.runs.length === 0) throw new Error(`${source}: runs must be a non-empty array`);
  value.runs.forEach((run, index) => validateRun(run, `${source}.runs[${index}]`));
  return value as unknown as CanonicalComparison;
}

export interface CanonicalArtifacts {
  summary: CanonicalRunSummary;
  summaries: CanonicalRunSummary[];
  comparisons: CanonicalComparison[];
}

function readJson(file: string): unknown {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    if (error instanceof SyntaxError) throw new Error(`${path.basename(file)}: invalid JSON`);
    throw error;
  }
}

function loadExternalArtifacts(directory: string): CanonicalArtifacts {
  const root = path.resolve(directory);
  const entries = readdirSync(root, { withFileTypes: true });
  const summaries = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(root, entry.name, "summary.json"))
    .filter((file) => existsSync(file) && statSync(file).isFile())
    .sort()
    .map((file) => validateRun(readJson(file), `${path.basename(path.dirname(file))}/summary.json`));
  if (summaries.length === 0) throw new Error(`No run summaries found in ${root}`);

  const comparisons = entries
    .filter((entry) => entry.isFile() && /^comparison-.*\.json$/.test(entry.name))
    .map((entry) => entry.name)
    .sort()
    .map((name) => validateComparison(readJson(path.join(root, name)), name));
  const summary = summaries.reduce((latest, current) => current.created_at_utc > latest.created_at_utc ? current : latest);
  return { summary, summaries, comparisons };
}

export function loadArtifacts(): CanonicalArtifacts {
  if (process.env.BENCHING_DATA_DIR) return loadExternalArtifacts(process.env.BENCHING_DATA_DIR);
  const summary = validateRun(summaryArtifact, "summary.json");
  return { summary, summaries: [summary], comparisons: [validateComparison(comparisonJanuary, "comparison-20260102.json")] };
}

export const artifacts = loadArtifacts();
