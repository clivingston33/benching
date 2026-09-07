import summaryArtifact from "@/data/summary.json";
import comparisonAugust from "@/data/comparison-20260828.json";
import comparisonSeptember from "@/data/comparison-20260901.json";
import { isCanonicalObject, type CanonicalComparison, type CanonicalRunSummary } from "@/lib/canonical-types";

function requiredRecord(value: Record<string, unknown>, key: string, source: string): Record<string, unknown> {
  const child = value[key];
  if (!isCanonicalObject(child)) throw new Error(`${source}: missing object "${key}"`);
  return child;
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
  if (!Array.isArray(value.tasks)) throw new Error(`${source}: tasks must be an array`);
  value.tasks.forEach((task, index) => {
    if (!isCanonicalObject(task) || typeof task.task_id !== "string" || typeof task.trial_id !== "string" || typeof task.request_id !== "string") throw new Error(`${source}: malformed task at index ${index}`);
  });
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
  comparisons: CanonicalComparison[];
}

export function loadArtifacts(): CanonicalArtifacts {
  const comparisons = [
    validateComparison(comparisonAugust, "comparison-20260828.json"),
    validateComparison(comparisonSeptember, "comparison-20260901.json"),
  ];
  return { summary: validateRun(summaryArtifact, "summary.json"), comparisons };
}

export const artifacts = loadArtifacts();
