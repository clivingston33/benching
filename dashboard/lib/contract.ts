import Ajv from "ajv/dist/2020";
// Single physical source: the Python producer owns these schemas at
// src/benching/benchmark/schemas/. They are bundled into the dashboard at
// build time via this static import, so production needs no Python runtime
// and no checked-in duplicate.
import comparisonSchema from "../../src/benching/benchmark/schemas/comparison-v1.schema.json";
import summarySchema from "../../src/benching/benchmark/schemas/summary-v1.schema.json";
import {
  isCanonicalObject,
  type CanonicalComparison,
  type CanonicalContextBucket,
  type CanonicalContextMetric,
  type CanonicalDistribution,
  type CanonicalRunSummary,
  type CanonicalTaskResult,
} from "@/lib/canonical-types";

const ajv = new Ajv({ allErrors: true, strict: true });
const validateSummarySchema = ajv.compile(summarySchema);
const validateComparisonSchema = ajv.compile(comparisonSchema);

export type ArtifactKind = "summary" | "comparison" | "unknown";
export type NoticeKind = "invalid" | "unsupported_version" | "unreadable";

export interface ArtifactNotice {
  file: string;
  kind: NoticeKind;
  reason: string;
}

/** Identify an artifact's kind and declared major version without validating. */
export function classifyArtifact(value: unknown): { kind: ArtifactKind; version: number | null } {
  if (!isCanonicalObject(value)) return { kind: "unknown", version: null };
  const version = typeof value.schema_version === "number" ? value.schema_version : null;
  if (Array.isArray(value.runs) && Array.isArray(value.run_ids)) return { kind: "comparison", version };
  if (typeof value.run_id === "string" && Array.isArray(value.tasks)) return { kind: "summary", version };
  return { kind: "unknown", version };
}

function ajvErrors(validate: { errors?: object[] | null }): string {
  const errors = (validate.errors ?? []) as Array<{ instancePath?: string; message?: string }>;
  const shown = errors.slice(0, 3).map((error) => `${error.instancePath || "<root>"} ${error.message ?? "invalid"}`);
  const extra = errors.length > 3 ? ` (+${errors.length - 3} more)` : "";
  return `${shown.join("; ")}${extra}`;
}

/** Schema errors for a summary document; empty when valid. */
export function summarySchemaErrors(value: unknown): string[] {
  if (!validateSummarySchema(value)) return [ajvErrors(validateSummarySchema)];
  return [];
}

/** Schema errors for a comparison shell; embedded runs are checked separately. */
export function comparisonSchemaErrors(value: unknown): string[] {
  if (!validateComparisonSchema(value)) return [ajvErrors(validateComparisonSchema)];
  return [];
}

/** Identity check JSON Schema cannot express: run_ids must match embedded ids. */
export function comparisonIdentityErrors(value: CanonicalComparison): string[] {
  const embedded = value.runs.map((run) => run.run_id);
  if (JSON.stringify(embedded) !== JSON.stringify(value.run_ids)) {
    return ["run_ids do not match embedded summary run ids"];
  }
  return [];
}

function projectDistribution(value: CanonicalDistribution): CanonicalDistribution {
  return {
    count: value.count ?? 0,
    mean: value.mean ?? null,
    median: value.median ?? null,
    min: value.min ?? null,
    max: value.max ?? null,
    p5: value.p5 ?? null,
    p25: value.p25 ?? null,
    p75: value.p75 ?? null,
    p90: value.p90 ?? null,
    p95: value.p95 ?? null,
    p99: value.p99 ?? null,
    stdev: value.stdev ?? null,
    cv: value.cv ?? null,
    p50: value.p50 ?? null,
  };
}

function projectContextMetric(value: CanonicalContextMetric | undefined): CanonicalContextMetric {
  const out: CanonicalContextMetric = { mean: value?.mean ?? null };
  if (value?.p50 !== undefined) out.p50 = value.p50;
  if (value?.p95 !== undefined) out.p95 = value.p95;
  return out;
}

function projectBucket(value: CanonicalContextBucket): CanonicalContextBucket {
  return {
    requests: value.requests ?? 0,
    ttft_ms: projectContextMetric(value.ttft_ms),
    decode_tps: projectContextMetric(value.decode_tps),
    end_to_end_latency_ms: projectContextMetric(value.end_to_end_latency_ms),
    failure_rate: value.failure_rate ?? null,
  };
}

function projectTask(value: CanonicalTaskResult): CanonicalTaskResult {
  return {
    task_id: value.task_id,
    trial_id: value.trial_id ?? null,
    passed: value.passed ?? null,
    reward: value.reward ?? null,
    duration_sec: value.duration_sec ?? null,
    exception: value.exception ?? null,
    timeout: value.timeout ?? null,
    requests: value.requests ?? 0,
    tokens: {
      input: value.tokens.input ?? null,
      output: value.tokens.output ?? null,
      cache_read: value.tokens.cache_read ?? null,
      cache_write: value.tokens.cache_write ?? null,
    },
    latency: {
      ttft_ms_mean: value.latency.ttft_ms_mean ?? null,
      ttft_ms_p50: value.latency.ttft_ms_p50 ?? null,
      ttft_ms_p95: value.latency.ttft_ms_p95 ?? null,
      end_to_end_latency_ms_mean: value.latency.end_to_end_latency_ms_mean ?? null,
    },
    reliability: {
      successful_requests: value.reliability.successful_requests ?? 0,
      failed_requests: value.reliability.failed_requests ?? 0,
      success_rate: value.reliability.success_rate ?? null,
    },
  };
}

/**
 * Project a validated summary to exactly the public contract fields.
 * Unknown/private extras (e.g. a stray `private_secret`) are dropped here,
 * so they can never reach browser serialization. Values are preserved
 * as-is: projection selects, never repairs or recomputes.
 */
export function projectSummary(value: CanonicalRunSummary): CanonicalRunSummary {
  const context: Record<string, CanonicalContextBucket> = {};
  for (const [name, bucket] of Object.entries(value.context ?? {})) {
    context[name] = projectBucket(bucket);
  }
  const projected: CanonicalRunSummary = {
    schema_version: value.schema_version,
    run_id: value.run_id,
    created_at_utc: value.created_at_utc,
    benchmark: { name: value.benchmark.name, version: value.benchmark.version, task_count: value.benchmark.task_count },
    provider: { id: value.provider.id, name: value.provider.name },
    model: value.model,
    reasoning: value.reasoning,
    execution: { concurrency: value.execution.concurrency, trials: value.execution.trials },
    score: {
      value: value.score.value ?? null,
      passed: value.score.passed ?? 0,
      failed: value.score.failed ?? 0,
      total: value.score.total ?? 0,
      success_rate: value.score.success_rate ?? null,
      errored: value.score.errored ?? 0,
      timeout: value.score.timeout ?? 0,
    },
    speed: {
      decode_tps: projectDistribution(value.speed.decode_tps),
      effective_tps: projectDistribution(value.speed.effective_tps),
      output_tps_mean: value.speed.output_tps_mean ?? null,
      output_tps_p50: value.speed.output_tps_p50 ?? null,
      output_tps_p95: value.speed.output_tps_p95 ?? null,
    },
    latency: {
      ttft_ms: projectDistribution(value.latency.ttft_ms),
      decode_duration_ms: projectDistribution(value.latency.decode_duration_ms),
      end_to_end_latency_ms: projectDistribution(value.latency.end_to_end_latency_ms),
      ttft_ms_mean: value.latency.ttft_ms_mean ?? null,
      ttft_ms_p50: value.latency.ttft_ms_p50 ?? null,
      ttft_ms_p95: value.latency.ttft_ms_p95 ?? null,
    },
    reliability: {
      successful_requests: value.reliability.successful_requests ?? 0,
      failed_requests: value.reliability.failed_requests ?? 0,
      success_rate: value.reliability.success_rate ?? null,
      request_success_rate: value.reliability.request_success_rate ?? null,
      stream_completion_rate: value.reliability.stream_completion_rate ?? null,
      http_error_rate: value.reliability.http_error_rate ?? null,
      timeout_rate: value.reliability.timeout_rate ?? null,
      provider_failures: value.reliability.provider_failures ?? 0,
      downstream_cancellations: value.reliability.downstream_cancellations ?? 0,
      incomplete_provider_streams: value.reliability.incomplete_provider_streams ?? 0,
      errors: value.reliability.errors ?? 0,
    },
    tokens: {
      input: value.tokens.input ?? null,
      output: value.tokens.output ?? null,
      input_provider: value.tokens.input_provider ?? null,
      output_provider: value.tokens.output_provider ?? null,
      total_provider: value.tokens.total_provider ?? null,
      cache_read: value.tokens.cache_read ?? null,
      cache_write: value.tokens.cache_write ?? null,
      output_local: value.tokens.output_local ?? null,
    },
    context,
    tasks: (value.tasks ?? []).map(projectTask),
  };
  if (value.metric_revision !== undefined) projected.metric_revision = value.metric_revision;
  if (value.tokenizer !== undefined) {
    projected.tokenizer = {
      repo: value.tokenizer.repo ?? null,
      revision: value.tokenizer.revision ?? null,
      available: value.tokenizer.available ?? null,
    };
  }
  return projected;
}

/** Project a validated comparison (and its embedded summaries) to public fields. */
export function projectComparison(value: CanonicalComparison): CanonicalComparison {
  const projected: CanonicalComparison = {
    schema_version: value.schema_version,
    created_at_utc: value.created_at_utc,
    benchmark: { name: value.benchmark.name, version: value.benchmark.version },
    run_ids: [...value.run_ids],
    models: [...value.models],
    execution_mode: value.execution_mode,
    official_comparison: value.official_comparison,
    tokenizers_comparable: value.tokenizers_comparable,
    runs: value.runs.map(projectSummary),
  };
  if (value.comparison_id !== undefined) projected.comparison_id = value.comparison_id;
  if (value.tokenizer_identity_status !== undefined) projected.tokenizer_identity_status = value.tokenizer_identity_status;
  return projected;
}
