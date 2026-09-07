export type ReasoningMode = "default" | "enabled" | "disabled";
export type ExecutionMode = "sequential" | "parallel";

export interface CanonicalMetric<T = number> {
  value: T | null;
  source: string;
}

export interface CanonicalDistribution {
  count: number;
  mean: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
  p5: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  stdev: number | null;
  cv: number | null;
  p50?: number | null;
}

export interface CanonicalBenchmark {
  name: string;
  version: string;
  task_count: number;
}

export interface CanonicalProvider {
  id: string;
  name: string;
}

export interface CanonicalExecution {
  concurrency: number;
  trials: number;
}

export interface CanonicalScore {
  value: number | null;
  passed: number;
  failed: number;
  total: number;
  success_rate: number | null;
  errored: number;
  timeout: number;
}

export interface CanonicalSpeed {
  decode_tps: CanonicalDistribution;
  effective_tps: CanonicalDistribution;
  output_tps_mean: number | null;
  output_tps_p50: number | null;
  output_tps_p95: number | null;
}

export interface CanonicalLatency {
  ttft_ms: CanonicalDistribution;
  decode_duration_ms: CanonicalDistribution;
  end_to_end_latency_ms: CanonicalDistribution;
  ttft_ms_mean: number | null;
  ttft_ms_p50: number | null;
  ttft_ms_p95: number | null;
}

export interface CanonicalReliability {
  successful_requests: number;
  failed_requests: number;
  success_rate: number | null;
  request_success_rate: number | null;
  stream_completion_rate: number | null;
  http_error_rate: number | null;
  timeout_rate: number | null;
  provider_failures: number;
  downstream_cancellations: number;
  incomplete_provider_streams: number;
  errors: number;
}

export interface CanonicalTokens {
  input: number | null;
  output: number | null;
  input_provider: number | null;
  output_provider: number | null;
  total_provider: number | null;
  cache_read: number | null;
  cache_write: number | null;
  output_local: number | null;
}

export interface CanonicalTaskTiming {
  ttft_ms?: CanonicalMetric;
  decode_duration_ms?: CanonicalMetric;
  end_to_end_latency_ms?: CanonicalMetric;
  decode_tps?: CanonicalMetric;
  effective_tps?: CanonicalMetric;
}

export interface CanonicalTaskTokens {
  input_provider?: CanonicalMetric;
  output_provider?: CanonicalMetric;
  total_provider?: CanonicalMetric;
  cache_read?: CanonicalMetric;
  cache_write?: CanonicalMetric;
  output_local?: CanonicalMetric;
}

export interface CanonicalTaskReliability {
  success: boolean;
  stream_completed?: boolean;
  downstream_cancelled?: boolean;
  provider_failure?: boolean;
  provider_stream_failure?: boolean;
  incomplete_provider_stream?: boolean;
  timeout?: boolean;
  error_type?: string | null;
  error_message?: string | null;
  http_status?: number | null;
}

export interface CanonicalTaskResult {
  task_id: string;
  trial_id: string;
  request_id: string;
  success: boolean;
  stream_completed: boolean;
  timing: CanonicalTaskTiming;
  tokens: CanonicalTaskTokens;
  reliability: CanonicalTaskReliability;
}

export interface CanonicalContextBucket {
  requests: number;
  ttft_ms: CanonicalDistribution;
  decode_tps: CanonicalDistribution;
  end_to_end_latency_ms?: CanonicalDistribution;
  failure_rate: number | null;
}

export function isCanonicalObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export interface CanonicalRunSummary {
  schema_version: number;
  run_id: string;
  created_at_utc: string;
  benchmark: CanonicalBenchmark;
  provider: CanonicalProvider;
  model: string;
  reasoning: ReasoningMode;
  execution: CanonicalExecution;
  score: CanonicalScore;
  speed: CanonicalSpeed;
  latency: CanonicalLatency;
  reliability: CanonicalReliability;
  tokens: CanonicalTokens;
  tasks: CanonicalTaskResult[];
  context?: Record<string, CanonicalContextBucket>;
}

export interface CanonicalComparison {
  schema_version: number;
  created_at_utc: string;
  benchmark: Omit<CanonicalBenchmark, "task_count">;
  run_ids: string[];
  models: string[];
  execution_mode: ExecutionMode;
  official_comparison: boolean;
  tokenizers_comparable: boolean;
  runs: CanonicalRunSummary[];
}
