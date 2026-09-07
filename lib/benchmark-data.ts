import summary from "@/data/summary.json";
import comparison from "@/data/comparison.json";

export interface Provider {
  id: string;
  name: string;
  color: string;
  logo?: string;
}

export interface Benchmark {
  id: string;
  name: string;
  totalTasks: number;
}

export interface ContextMetric {
  label: string;
  value: number | null;
}

export interface ScoreMetrics {
  value: number | null;
  passed: number;
  total: number;
}

export interface SpeedMetrics {
  outputTokensPerSecond: number | null;
  effectiveTokensPerSecond: number | null;
  byContext: ContextMetric[];
}

export interface LatencyMetrics {
  ttftMs: number | null;
  p95TtftMs: number | null;
  endToEndMs: number | null;
  byContext: ContextMetric[];
}

export interface ReliabilityMetrics {
  requests: number;
  successRate: number | null;
  streamCompletionRate: number | null;
  timeoutRate: number | null;
  errorRate: number | null;
  otherErrorRate: number | null;
  providerFailures: number;
  downstreamCancellations: number;
  incompleteStreams: number;
  byContext: ContextMetric[];
}

export interface TokenMetrics {
  input: number | null;
  output: number | null;
  cache: number | null;
}

export interface TaskResult {
  taskId: string;
  passed: boolean;
  reward: number | null;
  durationSec: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  cacheTokens: number | null;
  exception: string | null;
}

export interface RunSummary {
  runId: string;
  date: string;
  provider: Provider;
  model: string;
  benchmark: Benchmark;
  score: ScoreMetrics;
  speed: SpeedMetrics;
  latency: LatencyMetrics;
  reliability: ReliabilityMetrics;
  tokens: TokenMetrics;
  tasks: TaskResult[];
  badges: string[];
}

export interface ComparisonTaskResult {
  taskId: string;
  results: Record<string, TaskResult>;
}

export type ComparisonProvider = Omit<RunSummary, "runId" | "date" | "badges">;

export interface ComparisonRow {
  metric: string;
  values: Record<string, string>;
  note: string;
}

export interface Comparison {
  id: string;
  label: string;
  runIds: string[];
  providers: ComparisonProvider[];
  rows: ComparisonRow[];
  tasks: ComparisonTaskResult[];
}

interface SummaryDocument {
  generatedAt: string;
  providers: Provider[];
  benchmarks: Benchmark[];
  runs: RunSummary[];
}

interface ComparisonDocument {
  generatedAt: string;
  providers: Provider[];
  benchmarks: Benchmark[];
  comparisons: Comparison[];
}

export const summaryData = summary as SummaryDocument;
export const comparisonData = comparison as ComparisonDocument;
export const providers = comparisonData.providers;
export const benchmarks = comparisonData.benchmarks;
export const allRuns = summaryData.runs;
export const runDates = Array.from(new Set(allRuns.map((run) => run.date))).sort();
export const comparisons = comparisonData.comparisons;

export type RunSelection = "all" | string;

export function getComparison(selection: RunSelection): Comparison {
  const item = comparisons.find((candidate) => candidate.id === selection) ?? comparisons[0];
  if (!item) throw new Error("comparison.json contains no comparisons");
  return item;
}

export const comparisonRowsFor = (selection: RunSelection) => getComparison(selection).rows;
export const taskResultsFor = (selection: RunSelection) => getComparison(selection).tasks;

export function metricRowsFor(
  selection: RunSelection,
  metric: "score" | "outputTokensPerSecond" | "effectiveTokensPerSecond" | "ttftMs" | "endToEndMs" | "successRate" | "timeoutRate",
) {
  const item = getComparison(selection);
  const values = Object.fromEntries(item.providers.map((run) => {
    let value: number | null;
    if (metric === "score") value = run.score.value;
    else if (metric === "outputTokensPerSecond" || metric === "effectiveTokensPerSecond") value = run.speed[metric];
    else if (metric === "ttftMs" || metric === "endToEndMs") value = run.latency[metric];
    else value = run.reliability[metric];
    return [run.provider.id, value];
  }));
  const labels: Record<string, string> = {
    score: "Benchmark Score",
    outputTokensPerSecond: "Output Speed",
    effectiveTokensPerSecond: "Effective Speed",
    ttftMs: "Time to First Token",
    endToEndMs: "Response Time",
    successRate: "Success Rate",
    timeoutRate: "Timeout Rate",
  };
  return [{ bench: labels[metric], ...values }];
}

export function contextRowsFor(selection: RunSelection, metric: "speed" | "latency" | "reliability") {
  const item = getComparison(selection);
  const labels = Array.from(new Set(item.providers.flatMap((run) => run[metric].byContext.map((point) => point.label))));
  return labels.map((label) => ({
    label,
    ...Object.fromEntries(item.providers.map((run) => [run.provider.id, run[metric].byContext.find((point) => point.label === label)?.value ?? null])),
  }));
}


export function tokenRowsFor(selection: RunSelection) {
  const item = getComparison(selection);
  const keys = item.providers.flatMap((run) => [
    [`${run.provider.id}-input`, run.tokens.input],
    [`${run.provider.id}-output`, run.tokens.output],
    [`${run.provider.id}-cache`, run.tokens.cache],
  ] as const);
  return item.providers.map((run) => ({
    provider: run.provider.name,
    ...Object.fromEntries(keys.map(([key, value]) => [key, key.startsWith(`${run.provider.id}-`) ? value : 0])),
  }));
}

export function breakdownRowsFor(selection: RunSelection) {
  const item = getComparison(selection);
  return item.providers.map((run) => ({
    provider: run.provider.name,
    ...Object.fromEntries([
      [`${run.provider.id}-timeout`, run.reliability.timeoutRate],
      [`${run.provider.id}-other`, run.reliability.otherErrorRate],
    ]),
  }));
}

export function chartConfigFor(items = providers) {
  return Object.fromEntries(items.map((provider) => [provider.id, { label: provider.name, color: provider.color }]));
}

export function tokenConfigFor(selection: RunSelection) {
  return Object.fromEntries(
    getComparison(selection).providers.flatMap((run) => [
      [`${run.provider.id}-input`, { label: `${run.provider.name} Input`, color: run.provider.color }],
      [`${run.provider.id}-output`, { label: `${run.provider.name} Output`, color: run.provider.color }],
      [`${run.provider.id}-cache`, { label: `${run.provider.name} Cache`, color: run.provider.color }],
    ]),
  );
}

export function breakdownConfigFor(selection: RunSelection) {
  return Object.fromEntries(
    getComparison(selection).providers.flatMap((run) => [
      [`${run.provider.id}-timeout`, { label: `${run.provider.name} Timeout`, color: run.provider.color }],
      [`${run.provider.id}-other`, { label: `${run.provider.name} Other`, color: `${run.provider.color}99` }],
    ]),
  );
}

export const fmtRunLabel = (date: string) => {
  const value = new Date(`${date}T00:00:00Z`);
  return value.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};

export function fmtDuration(sec: number | null): string {
  if (sec == null) return "n/a";
  const minutes = Math.floor(sec / 60);
  return `${minutes}m ${String(Math.round(sec % 60)).padStart(2, "0")}s`;
}

export const fmtTokens = (value: number | null) => (value == null ? "n/a" : Math.round(value / 1000) + "K");
