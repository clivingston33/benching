import { artifacts } from "@/lib/artifact-loader";
import { presentationFor } from "@/lib/provider-presentation";
import type { CanonicalComparison, CanonicalRunSummary, CanonicalTaskResult } from "@/lib/canonical-types";

export type {
  CanonicalBenchmark as Benchmark,
  CanonicalComparison,
  CanonicalContextBucket,
  CanonicalDistribution,
  CanonicalLatency,
  CanonicalMetric,
  CanonicalProvider as Provider,
  CanonicalReliability,
  CanonicalRunSummary as RunSummary,
  CanonicalScore,
  CanonicalSpeed,
  CanonicalTaskResult,
  CanonicalTokens,
} from "@/lib/canonical-types";

export const summaryData = artifacts.summary;
export const comparisons = artifacts.comparisons;
export const allRuns = Array.from(new Map([...comparisons.flatMap((comparison) => comparison.runs), summaryData].map((run) => [run.run_id, run])).values());
export const providers = Array.from(new Map(allRuns.map((run, index) => [run.provider.id, presentationFor(run.provider, index)])).values());
export const benchmarks = Array.from(new Map(allRuns.map((run) => [`${run.benchmark.name}:${run.benchmark.version}`, run.benchmark])).values());

export type RunSelection = string;
export const comparisonOptions = comparisons.map((comparison, index) => ({ selection: `comparison:${index}`, label: formatComparisonLabel(comparison), comparison }));
export const runOptions = allRuns.map((run) => ({ selection: `run:${run.run_id}`, label: `${formatDate(run.created_at_utc)} · ${run.provider.name}`, run }));

export interface SelectedComparison {
  source: CanonicalComparison;
  runs: CanonicalRunSummary[];
  label: string;
}

export function getComparison(selection: RunSelection): SelectedComparison {
  if (selection.startsWith("run:")) {
    const runId = selection.slice(4);
    const run = allRuns.find((candidate) => candidate.run_id === runId);
    if (!run) throw new Error(`Unknown run selection: ${runId}`);
    const source = comparisons.find((candidate) => candidate.run_ids.includes(runId));
    if (!source) throw new Error(`No comparison artifact contains run ${runId}`);
    return { source, runs: [run], label: `${formatDate(run.created_at_utc)} · ${run.provider.name}` };
  }
  const index = Number(selection.slice("comparison:".length));
  const source = comparisons[index];
  if (!source) throw new Error(`Unknown comparison selection: ${selection}`);
  return { source, runs: source.runs, label: formatComparisonLabel(source) };
}

export function comparisonRowsFor(selection: RunSelection) {
  const { runs } = getComparison(selection);
  const fields = [
    ["Median Output Speed", (run: CanonicalRunSummary) => run.speed.decode_tps.median, (value: number | null) => formatNumber(value, " tok/s")],
    ["Median Time to First Token", (run: CanonicalRunSummary) => run.latency.ttft_ms.median, (value: number | null) => formatNumber(value, " ms")],
    ["P95 Time to First Token", (run: CanonicalRunSummary) => run.latency.ttft_ms.p95, (value: number | null) => formatNumber(value, " ms")],
    ["Median End-to-End Time", (run: CanonicalRunSummary) => run.latency.end_to_end_latency_ms.median, (value: number | null) => formatNumber(value, " ms")],
    ["Request Success Rate", (run: CanonicalRunSummary) => run.reliability.request_success_rate, formatPercent],
    ["Stream Completion Rate", (run: CanonicalRunSummary) => run.reliability.stream_completion_rate, formatPercent],
    ["Timeout Rate", (run: CanonicalRunSummary) => run.reliability.timeout_rate, formatPercent],
  ] as const;
  return fields.map(([metric, valueFor, format]) => ({ metric, values: Object.fromEntries(runs.map((run) => [run.provider.id, format(valueFor(run))])), note: "" }));
}

export function metricRowsFor(selection: RunSelection, metric: "score" | "decode_tps" | "effective_tps" | "ttft_ms" | "end_to_end_latency_ms" | "request_success_rate" | "timeout_rate") {
  const { runs } = getComparison(selection);
  return [{
    bench: metricLabel(metric),
    ...Object.fromEntries(runs.map((run) => [run.provider.id, metricValue(run, metric)])),
  }];
}

function metricValue(run: CanonicalRunSummary, metric: string): number | null {
  if (metric === "score") return run.score.value == null ? null : run.score.value * 100;
  if (metric === "decode_tps") return run.speed.decode_tps.median;
  if (metric === "effective_tps") return run.speed.effective_tps.median;
  if (metric === "ttft_ms") return run.latency.ttft_ms.median;
  if (metric === "end_to_end_latency_ms") return run.latency.end_to_end_latency_ms.median;
  if (metric === "request_success_rate") return run.reliability.request_success_rate == null ? null : run.reliability.request_success_rate * 100;
  return run.reliability.timeout_rate == null ? null : run.reliability.timeout_rate * 100;
}

function metricLabel(metric: string): string {
  const labels: Record<string, string> = { score: "Benchmark Score", decode_tps: "Output Speed", effective_tps: "Effective Speed", ttft_ms: "Time to First Token", end_to_end_latency_ms: "Response Time", request_success_rate: "Success Rate", timeout_rate: "Timeout Rate" };
  return labels[metric] ?? metric;
}

export function contextRowsFor(selection: RunSelection, metric: "speed" | "latency" | "reliability") {
  const { runs } = getComparison(selection);
  const buckets = runs.map((run) => run.context ?? {});
  const labels = Array.from(new Set(buckets.flatMap((context) => Object.keys(context))));
  return labels.map((label) => ({
    label,
    ...Object.fromEntries(runs.map((run) => [run.provider.id, contextValue(run, metric, label)])),
  }));
}

function contextValue(run: CanonicalRunSummary, metric: "speed" | "latency" | "reliability", label: string): number | null {
  const bucket = run.context?.[label];
  if (!bucket) return null;
  if (metric === "speed") return bucket.decode_tps.median;
  if (metric === "latency") return bucket.ttft_ms.median;
  return bucket.failure_rate == null ? null : bucket.failure_rate * 100;
}

export interface ComparisonTaskResult {
  taskId: string;
  trialId: string;
  results: Record<string, CanonicalTaskResult | undefined>;
}

export function taskResultsFor(selection: RunSelection): ComparisonTaskResult[] {
  const { runs } = getComparison(selection);
  const groups = new Map<string, ComparisonTaskResult>();
  runs.forEach((run) => run.tasks.forEach((task) => {
    const key = `${task.task_id}:${task.trial_id}`;
    const group = groups.get(key) ?? { taskId: task.task_id, trialId: task.trial_id, results: {} };
    group.results[run.provider.id] = task;
    groups.set(key, group);
  }));
  return Array.from(groups.values()).sort((a, b) => `${a.taskId}:${a.trialId}`.localeCompare(`${b.taskId}:${b.trialId}`));
}

export function tokenRowsFor(selection: RunSelection) {
  const { runs } = getComparison(selection);
  const keys = runs.flatMap((run) => [`${run.provider.id}-input`, `${run.provider.id}-output`, `${run.provider.id}-cache`]);
  return runs.map((run) => ({
    provider: run.provider.name,
    ...Object.fromEntries(keys.map((key) => [key, key.startsWith(`${run.provider.id}-`) ? tokenValue(run, key.slice(run.provider.id.length + 1)) : null])),
  }));
}

function tokenValue(run: CanonicalRunSummary, metric: string): number | null {
  if (metric === "input") return run.tokens.input;
  if (metric === "output") return run.tokens.output;
  return run.tokens.cache_read;
}

export function breakdownRowsFor(selection: RunSelection) {
  const { runs } = getComparison(selection);
  return runs.map((run) => ({ provider: run.provider.name, [`${run.provider.id}-timeout`]: toPercent(run.reliability.timeout_rate), [`${run.provider.id}-errors`]: toPercent(run.reliability.http_error_rate) }));
}

export function chartConfigFor(runs: CanonicalRunSummary[] | typeof providers = providers) {
  return Object.fromEntries(runs.map((item, index) => {
    const provider = "provider" in item ? presentationFor(item.provider, index) : item;
    return [provider.id, { label: provider.name, color: provider.color }];
  }));
}

export function tokenConfigFor(selection: RunSelection) {
  return Object.fromEntries(getComparison(selection).runs.flatMap((run, index) => {
    const provider = presentationFor(run.provider, index);
    return [[`${provider.id}-input`, { label: `${provider.name} Input`, color: provider.color }], [`${provider.id}-output`, { label: `${provider.name} Output`, color: provider.color }], [`${provider.id}-cache`, { label: `${provider.name} Cache`, color: provider.color }]];
  }));
}

export function breakdownConfigFor(selection: RunSelection) {
  return Object.fromEntries(getComparison(selection).runs.flatMap((run, index) => {
    const provider = presentationFor(run.provider, index);
    return [[`${provider.id}-timeout`, { label: `${provider.name} Timeout`, color: provider.color }], [`${provider.id}-errors`, { label: `${provider.name} HTTP errors`, color: `${provider.color}99` }]];
  }));
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function formatComparisonLabel(comparison: CanonicalComparison) {
  return `${formatDate(comparison.created_at_utc)} comparison`;
}

function formatNumber(value: number | null, suffix: string) { return value == null ? "n/a" : `${Math.round(value).toLocaleString()}${suffix}`; }
function formatPercent(value: number | null) { return value == null ? "n/a" : `${(value * 100).toFixed(2)}%`; }
function toPercent(value: number | null) { return value == null ? null : value * 100; }

export function fmtDuration(task: CanonicalTaskResult | undefined) {
  const value = task?.timing.end_to_end_latency_ms?.value;
  if (value == null) return "n/a";
  const minutes = Math.floor(value / 60000);
  return `${minutes}m ${String(Math.round(value / 1000) % 60).padStart(2, "0")}s`;
}

export function fmtTokens(value: number | null | undefined) { return value == null ? "n/a" : `${Math.round(value / 1000)}K`; }
