import { presentationFor } from "@/lib/provider-presentation";
import type { CanonicalArtifacts } from "@/lib/artifact-loader";
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

export type RunSelection = string;

export interface RunSeries {
  /** Canonical data key: the run id. Never a provider id. */
  key: string;
  run: CanonicalRunSummary;
  /** Display label, disambiguated when provider+model repeat. */
  label: string;
  name: string;
  model: string;
  /** Time/short-id suffix when another run shares provider+model, else null. */
  disambiguator: string | null;
  color: string;
  logo?: string;
}

export interface ArtifactDataset {
  summary: CanonicalRunSummary | null;
  summaries: CanonicalRunSummary[];
  comparisons: CanonicalComparison[];
  allRuns: CanonicalRunSummary[];
  providers: Array<{ id: string; name: string; color: string; logo?: string }>;
  comparisonOptions: Array<{ selection: string; label: string }>;
  runOptions: Array<{ selection: string; label: string }>;
}

/** Provider+model display label, disambiguated by time and short id on repeats. Presentation only. */
export function runDisplayLabel(run: CanonicalRunSummary, runs: CanonicalRunSummary[]): string {
  const base = `${run.provider.name} · ${run.model}`;
  const dupes = runs.filter((other) => other.provider.id === run.provider.id && other.model === run.model);
  if (dupes.length <= 1) return base;
  const time = formatTime(run.created_at_utc);
  const label = `${base} · ${time}`;
  if (dupes.filter((other) => formatTime(other.created_at_utc) === time).length <= 1) return label;
  return `${label} · ${run.run_id.slice(-4)}`;
}

function disambiguatorFor(run: CanonicalRunSummary, runs: CanonicalRunSummary[]): string | null {
  const base = `${run.provider.name} · ${run.model}`;
  const dupes = runs.filter((other) => other.provider.id === run.provider.id && other.model === run.model);
  if (dupes.length <= 1) return null;
  const time = formatTime(run.created_at_utc);
  if (dupes.filter((other) => formatTime(other.created_at_utc) === time).length <= 1) return time;
  return `${time} · ${run.run_id.slice(-4)}`;
}

/** One series per run, keyed by run id. Provider identity is presentation metadata only. */
export function seriesFor(runs: CanonicalRunSummary[]): RunSeries[] {
  return runs.map((run, index) => {
    const presentation = presentationFor(run.provider, index);
    return {
      key: run.run_id,
      run,
      label: runDisplayLabel(run, runs),
      name: presentation.name,
      model: run.model,
      disambiguator: disambiguatorFor(run, runs),
      color: presentation.color,
      logo: presentation.logo,
    };
  });
}

/** Pure derivation: validated immutable artifacts in, frozen dataset out. No module state. */
export function createDataset(data: CanonicalArtifacts): ArtifactDataset {
  const comparisons = [...data.comparisons];
  const standaloneById = new Map(data.summaries.map((run) => [run.run_id, run]));
  const embeddedById = new Map(comparisons.flatMap((comparison) => comparison.runs).map((run) => [run.run_id, run]));
  // Canonical standalone summaries win over embedded snapshots: reanalysis
  // refreshes standalone files while comparison embeddings stay frozen.
  const allRuns = Array.from(new Map([...embeddedById, ...standaloneById]).values());
  const providers = Array.from(new Map(allRuns.map((run, index) => [run.provider.id, presentationFor(run.provider, index)])).values());
  const comparisonOptions = comparisons.map((comparison) => ({
    selection: `comparison:${comparison.comparison_id ?? comparison.run_ids.join("+")}`,
    label: formatComparisonLabel(comparison),
    comparison,
  }));
  const runOptions = allRuns.map((run) => ({
    selection: `run:${run.run_id}`,
    label: `${formatDate(run.created_at_utc)} · ${runDisplayLabel(run, allRuns)}`,
    run,
  }));
  return { summary: data.summary, summaries: [...data.summaries], comparisons, allRuns, providers, comparisonOptions, runOptions };
}

export function defaultSelection(dataset: ArtifactDataset): RunSelection {
  return dataset.comparisonOptions[0]?.selection ?? dataset.runOptions[0]?.selection ?? "";
}

export function hasSelection(dataset: ArtifactDataset, selection: RunSelection): boolean {
  return (
    dataset.comparisonOptions.some((item) => item.selection === selection) ||
    dataset.runOptions.some((item) => item.selection === selection)
  );
}

export function selectionLabel(dataset: ArtifactDataset, selection: RunSelection): string {
  return (
    dataset.comparisonOptions.find((item) => item.selection === selection)?.label ??
    dataset.runOptions.find((item) => item.selection === selection)?.label ??
    "No artifact selected"
  );
}

export interface SelectedComparison {
  source: CanonicalComparison;
  runs: CanonicalRunSummary[];
  label: string;
}

export function getComparison(dataset: ArtifactDataset, selection: RunSelection): SelectedComparison {
  const { allRuns, comparisons } = dataset;
  if (selection.startsWith("run:")) {
    const runId = selection.slice(4);
    const run = allRuns.find((candidate) => candidate.run_id === runId);
    if (!run) throw new Error(`Unknown run selection: ${runId}`);
    const source: CanonicalComparison = comparisons.find((candidate) => candidate.run_ids.includes(runId)) ?? {
      schema_version: 1,
      created_at_utc: run.created_at_utc,
      benchmark: run.benchmark,
      run_ids: [run.run_id],
      models: [run.model],
      execution_mode: "sequential",
      official_comparison: false,
      tokenizers_comparable: false,
      runs: [run],
    };
    return { source, runs: [run], label: `${formatDate(run.created_at_utc)} · ${run.provider.name}` };
  }
  const rest = selection.slice("comparison:".length);
  const source =
    comparisons.find((candidate) => (candidate.comparison_id ?? candidate.run_ids.join("+")) === rest) ??
    comparisons.find((candidate) => candidate.run_ids.join("+") === rest) ??
    (/^\d+$/.test(rest) ? comparisons[Number(rest)] : undefined);
  if (!source) throw new Error(`Unknown comparison selection: ${selection}`);
  return { source, runs: source.runs, label: formatComparisonLabel(source) };
}

export function comparisonRowsFor(dataset: ArtifactDataset, selection: RunSelection) {
  const { runs } = getComparison(dataset, selection);
  const fields = [
    ["Median Output Speed", (run: CanonicalRunSummary) => run.speed.decode_tps.p50, (value: number | null | undefined) => formatNumber(value, " tok/s")],
    ["Median Time to First Token", (run: CanonicalRunSummary) => run.latency.ttft_ms.p50, (value: number | null | undefined) => formatNumber(value, " ms")],
    ["P95 Time to First Token", (run: CanonicalRunSummary) => run.latency.ttft_ms.p95, (value: number | null | undefined) => formatNumber(value, " ms")],
    ["Median End-to-End Time", (run: CanonicalRunSummary) => run.latency.end_to_end_latency_ms.p50, (value: number | null | undefined) => formatNumber(value, " ms")],
    ["Request Success Rate", (run: CanonicalRunSummary) => run.reliability.request_success_rate, formatPercent],
    ["Stream Completion Rate", (run: CanonicalRunSummary) => run.reliability.stream_completion_rate, formatPercent],
    ["Timeout Rate", (run: CanonicalRunSummary) => run.reliability.timeout_rate, formatPercent],
  ] as const;
  return fields.map(([metric, valueFor, format]) => ({ metric, values: Object.fromEntries(runs.map((run) => [run.run_id, format(valueFor(run))])), note: "" }));
}

export function metricRowsFor(dataset: ArtifactDataset, selection: RunSelection, metric: "score" | "decode_tps" | "effective_tps" | "ttft_ms" | "end_to_end_latency_ms" | "request_success_rate" | "timeout_rate") {
  const { runs } = getComparison(dataset, selection);
  return [{
    bench: metricLabel(metric),
    ...Object.fromEntries(runs.map((run) => [run.run_id, metricValue(run, metric)])),
  }];
}

function metricValue(run: CanonicalRunSummary, metric: string): number | null {
  if (metric === "score") return run.score.value == null ? null : run.score.value * 100;
  if (metric === "decode_tps") return run.speed.decode_tps.p50 ?? null;
  if (metric === "effective_tps") return run.speed.effective_tps.p50 ?? null;
  if (metric === "ttft_ms") return run.latency.ttft_ms.p50 ?? null;
  if (metric === "end_to_end_latency_ms") return run.latency.end_to_end_latency_ms.p50 ?? null;
  if (metric === "request_success_rate") return run.reliability.request_success_rate == null ? null : run.reliability.request_success_rate * 100;
  return run.reliability.timeout_rate == null ? null : run.reliability.timeout_rate * 100;
}

function metricLabel(metric: string): string {
  const labels: Record<string, string> = { score: "Benchmark Score", decode_tps: "Output Speed", effective_tps: "Effective Speed", ttft_ms: "Time to First Token", end_to_end_latency_ms: "Response Time", request_success_rate: "Success Rate", timeout_rate: "Timeout Rate" };
  return labels[metric] ?? metric;
}

export function contextRowsFor(dataset: ArtifactDataset, selection: RunSelection, metric: "speed" | "latency" | "reliability") {
  const { runs } = getComparison(dataset, selection);
  const buckets = runs.map((run) => run.context ?? {});
  const labels = Array.from(new Set(buckets.flatMap((context) => Object.keys(context))));
  return labels.map((label) => ({
    label,
    ...Object.fromEntries(runs.map((run) => [run.run_id, contextValue(run, metric, label)])),
  }));
}

function contextValue(run: CanonicalRunSummary, metric: "speed" | "latency" | "reliability", label: string): number | null {
  const bucket = run.context?.[label];
  if (!bucket) return null;
  if (metric === "speed") return bucket.decode_tps.p50 ?? null;
  if (metric === "latency") return bucket.ttft_ms.p50 ?? null;
  return bucket.failure_rate == null ? null : bucket.failure_rate * 100;
}

export interface ComparisonTaskResult {
  taskId: string;
  trialId: string | null;
  results: Record<string, CanonicalTaskResult | undefined>;
}

export function taskResultsFor(dataset: ArtifactDataset, selection: RunSelection): ComparisonTaskResult[] {
  const { runs } = getComparison(dataset, selection);
  const groups = new Map<string, ComparisonTaskResult>();
  runs.forEach((run) => run.tasks.forEach((task) => {
    const key = `${task.task_id}:${task.trial_id ?? "unknown"}`;
    const group = groups.get(key) ?? { taskId: task.task_id, trialId: task.trial_id, results: {} };
    group.results[run.run_id] = task;
    groups.set(key, group);
  }));
  return Array.from(groups.values()).sort((a, b) => `${a.taskId}:${a.trialId}`.localeCompare(`${b.taskId}:${b.trialId}`));
}

export function tokenRowsFor(dataset: ArtifactDataset, selection: RunSelection) {
  const { runs } = getComparison(dataset, selection);
  const keys = runs.flatMap((run) => [`${run.run_id}-input`, `${run.run_id}-output`, `${run.run_id}-cache`]);
  return seriesFor(runs).map((item) => ({
    provider: item.label,
    ...Object.fromEntries(keys.map((key) => [key, key.startsWith(`${item.key}-`) ? tokenValue(item.run, key.slice(item.key.length + 1)) : null])),
  }));
}

function tokenValue(run: CanonicalRunSummary, metric: string): number | null {
  if (metric === "input") return run.tokens.input;
  if (metric === "output") return run.tokens.output;
  return run.tokens.cache_read;
}

export function breakdownRowsFor(dataset: ArtifactDataset, selection: RunSelection) {
  const { runs } = getComparison(dataset, selection);
  return seriesFor(runs).map((item) => ({ provider: item.label, [`${item.key}-timeout`]: toPercent(item.run.reliability.timeout_rate), [`${item.key}-errors`]: toPercent(item.run.reliability.http_error_rate) }));
}

export function chartConfigFor(runs: CanonicalRunSummary[]) {
  return Object.fromEntries(seriesFor(runs).map((item) => [item.key, { label: item.label, color: item.color }]));
}

export function tokenConfigFor(dataset: ArtifactDataset, selection: RunSelection) {
  const runs = getComparison(dataset, selection).runs;
  return Object.fromEntries(seriesFor(runs).flatMap((item) => [
    [`${item.key}-input`, { label: `${item.label} Input`, color: item.color }],
    [`${item.key}-output`, { label: `${item.label} Output`, color: item.color }],
    [`${item.key}-cache`, { label: `${item.label} Cache`, color: item.color }],
  ]));
}

export function breakdownConfigFor(dataset: ArtifactDataset, selection: RunSelection) {
  const runs = getComparison(dataset, selection).runs;
  return Object.fromEntries(seriesFor(runs).flatMap((item) => [
    [`${item.key}-timeout`, { label: `${item.label} Timeout`, color: item.color }],
    [`${item.key}-errors`, { label: `${item.label} HTTP errors`, color: `${item.color}99` }],
  ]));
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function formatTime(value: string) {
  const date = new Date(value);
  const hours = String(date.getUTCHours()).padStart(2, "0");
  const minutes = String(date.getUTCMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

function formatComparisonLabel(comparison: CanonicalComparison) {
  return `${formatDate(comparison.created_at_utc)} comparison`;
}

function formatNumber(value: number | null | undefined, suffix: string) { return value == null ? "n/a" : `${Math.round(value).toLocaleString()}${suffix}`; }
function formatPercent(value: number | null | undefined) { return value == null ? "n/a" : `${(value * 100).toFixed(2)}%`; }
function toPercent(value: number | null | undefined) { return value == null ? null : value * 100; }

export function fmtDuration(task: CanonicalTaskResult | undefined) {
  const value = task?.duration_sec;
  if (value == null) return "n/a";
  const minutes = Math.floor(value / 60);
  return `${minutes}m ${String(Math.round(value) % 60).padStart(2, "0")}s`;
}

export function fmtTokens(value: number | null | undefined) { return value == null ? "n/a" : `${Math.round(value / 1000)}K`; }
