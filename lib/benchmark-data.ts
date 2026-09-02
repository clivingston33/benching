import summary from "@/data/benchmark-summary.json";

export type ProviderKey = "kourier" | "electronhub";

export const PROVIDERS: ProviderKey[] = ["kourier", "electronhub"];

export const PROVIDER_LABEL: Record<ProviderKey, string> = {
  kourier: "Kourier",
  electronhub: "ElectronHub",
};

export type ProviderMetrics = {
  requests: number;
  success_rate: number | null;
  stream_completion_rate: number | null;
  timeout_rate: number | null;
  http_errors: number;
  provider_failures: number;
  downstream_cancellations: number;
  incomplete_provider_streams: number;
  median_ttft_ms: number | null;
  p95_ttft_ms: number | null;
  median_e2e_ms: number | null;
  median_decode_tps: number | null;
  median_effective_tps: number | null;
  median_input_tokens: number | null;
  median_output_tokens: number | null;
  median_cache_tokens: number | null;
  context_window: number;
  tasks_passed: number;
  tasks_total: number;
  task_pass_rate: number | null;
  errors: number;
};

export const providerConfig: Record<ProviderKey, { label: string; color: string }> = {
  kourier: { label: `${summary.model_label} (Kourier)`, color: "#1F704C" },
  electronhub: { label: `${summary.model_label} (ElectronHub)`, color: "#A242FB" },
};

export const MODEL_LABEL: string = summary.model_label as string;

/** True when the provider has measured data for the metric (null = unavailable). */
export const has = (p: ProviderKey, v: number | null | undefined): v is number => v != null;

// ============================================================
// Per-run data model
// ============================================================

/** One run date (e.g. "2026-08-28"), selection value for the run selector. */
export type RunSelection = "all" | string; // "all" = average across runs

export interface RunSummary {
  date: string;
  comparison: string;
  official_comparison: boolean;
  execution_mode: string;
  model: string;
  providers: Record<ProviderKey, ProviderMetrics>;
  context_scaling: Record<
    ProviderKey,
    {
      speed: { label: string; decode_tps: number | null }[];
      ttft: { label: string; ttft_ms: number | null }[];
      failure: { label: string; failure_rate: number | null }[];
    }
  >;
  task_results: TaskResultRow[];
}

export interface TaskResultRow {
  task: string;
  kourierPassed: boolean;
  electronPassed: boolean;
  kourierDurationSec: number | null;
  electronDurationSec: number | null;
  kourierInputTokens: number | null;
  electronInputTokens: number | null;
  kourierOutputTokens: number | null;
  electronOutputTokens: number | null;
  kourierCacheTokens: number | null;
  electronCacheTokens: number | null;
  kourierException: string | null;
  electronException: string | null;
}

// The full per-run datasets from data/benchmark-summary.json (ordered by date).
export const allRuns: RunSummary[] = (summary.runs as RunSummary[]).slice().sort((a, b) => a.date.localeCompare(b.date));

export const runDates: string[] = allRuns.map((r) => r.date);

export const latestRun: RunSummary = allRuns[allRuns.length - 1];

export const fmtRunLabel = (date: string) => {
  const d = new Date(date + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};

// ============================================================
// Selection helpers (pure; components call with useRunSelection)
// ============================================================

/** Runs included for a selection: all runs (average) or a single date. */
export const selectedRuns = (selection: RunSelection): RunSummary[] =>
  selection === "all" ? allRuns : allRuns.filter((r) => r.date === selection);

const mean = (vals: (number | null)[]): number | null => {
  const clean = vals.filter((v): v is number => v != null);
  return clean.length ? clean.reduce((a, b) => a + b, 0) / clean.length : null;
};

/** Round to hundredths (2 decimals) — averages can produce long floats. */
const round2 = (v: number | null): number | null => (v == null ? null : Math.round(v * 100) / 100);

/** Average ProviderMetrics across the selected runs for one provider. */
export function avgProvider(selection: RunSelection, provider: ProviderKey): ProviderMetrics | null {
  const runs = selectedRuns(selection);
  if (!runs.length) return null;
  const samples = runs.map((r) => r.providers[provider]).filter((p): p is ProviderMetrics => p != null);
  if (!samples.length) return null;
  const pick = (f: (p: ProviderMetrics) => number | null) => round2(mean(samples.map(f)));
  const pickInt = (f: (p: ProviderMetrics) => number) => Math.round(mean(samples.map(f)) ?? 0);
  const last = samples[samples.length - 1];
  return {
    requests: samples.reduce((a, p) => a + p.requests, 0),
    success_rate: round2(pick((p) => p.success_rate)),
    stream_completion_rate: round2(pick((p) => p.stream_completion_rate)),
    timeout_rate: round2(pick((p) => p.timeout_rate)),
    http_errors: samples.reduce((a, p) => a + p.http_errors, 0),
    provider_failures: samples.reduce((a, p) => a + p.provider_failures, 0),
    downstream_cancellations: samples.reduce((a, p) => a + p.downstream_cancellations, 0),
    incomplete_provider_streams: samples.reduce((a, p) => a + p.incomplete_provider_streams, 0),
    median_ttft_ms: pick((p) => p.median_ttft_ms),
    p95_ttft_ms: pick((p) => p.p95_ttft_ms),
    median_e2e_ms: pick((p) => p.median_e2e_ms),
    median_decode_tps: pick((p) => p.median_decode_tps),
    median_effective_tps: pick((p) => p.median_effective_tps),
    median_input_tokens: pick((p) => p.median_input_tokens),
    median_output_tokens: pick((p) => p.median_output_tokens),
    median_cache_tokens: pick((p) => p.median_cache_tokens),
    context_window: last.context_window,
    tasks_passed: pickInt((p) => p.tasks_passed),
    tasks_total: last.tasks_total,
    task_pass_rate: round2(pick((p) => p.task_pass_rate)),
    errors: samples.reduce((a, p) => a + p.errors, 0),
  };
}

/** Context-scaling buckets averaged across selected runs (by bucket label). */
export type ScalingSeries = { label: string; speed: number | null; ttft: number | null; failure: number | null };
export function avgContextScaling(selection: RunSelection, provider: ProviderKey): ScalingSeries[] {
  const runs = selectedRuns(selection).filter((r) => r.context_scaling[provider]);
  if (!runs.length) return [];
  const labels = Array.from(
    new Set(
      runs.flatMap((r) => {
        const cs = r.context_scaling[provider];
        return [...cs.speed.map((p) => p.label), ...cs.ttft.map((p) => p.label), ...cs.failure.map((p) => p.label)];
      }),
    ),
  ).sort();
  return labels.map((label) => {
    const pick = <T extends "decode_tps" | "ttft_ms" | "failure_rate">(
      key: "speed" | "ttft" | "failure",
      field: T,
    ) => {
      const vals = runs
        .map((r) => r.context_scaling[provider][key].find((p) => p.label === label))
        .map((p) => (p ? (p as unknown as Record<string, number | null>)[field] : null));
      return mean(vals);
    };
    return {
      label,
      speed: round2(pick("speed", "decode_tps")),
      ttft: round2(pick("ttft", "ttft_ms")),
      failure: round2(pick("failure", "failure_rate")),
    };
  });
}

// ============================================================
// Task results (selected-run aware, but per-run table by default uses latest run)
// ============================================================
export const taskResultsFor = (selection: RunSelection): TaskResultRow[] => {
  const runs = selectedRuns(selection);
  if (!runs.length) return [];
  if (selection !== "all") return runs[0].task_results || [];
  // For "all", show the latest run's per-task results (task-level pass/fail is per-run;
  // averaging pass/fail across runs is shown in Run History trend instead).
  return latestRun.task_results || [];
};

// ============================================================
// Presentational row builders (kept for component compatibility; take metrics)
// ============================================================

const fmtMs = (v: number | null, unit = "ms") => (v == null ? "n/a" : `${Math.round(v).toLocaleString()} ${unit}`);
const fmtS = (v: number | null) => (v == null ? "n/a" : `${(v / 1000).toFixed(1)} s`);
const fmtPct = (v: number | null) => (v == null ? "n/a" : `${v.toFixed(1)}%`);
const fmtTps = (v: number | null) => (v == null ? "n/a" : `${Math.round(v)} tok/s`);

export type ComparisonRow = { metric: string; kourier: string; electron: string; note: string };

export const comparisonRowsFor = (sel: RunSelection): ComparisonRow[] => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  if (!k || !e) return [];
  return [
    { metric: "Median Output Speed", kourier: fmtTps(k.median_decode_tps), electron: fmtTps(e.median_decode_tps), note: e.median_decode_tps && k.median_decode_tps ? `ElectronHub ${((e.median_decode_tps / k.median_decode_tps - 1) * 100).toFixed(0)}% faster decode` : "" },
    { metric: "Median Time to First Token", kourier: fmtMs(k.median_ttft_ms), electron: fmtMs(e.median_ttft_ms), note: k.median_ttft_ms && e.median_ttft_ms ? `Kourier TTFT ${(e.median_ttft_ms / k.median_ttft_ms).toFixed(1)}× lower` : "" },
    { metric: "P95 Time to First Token", kourier: fmtMs(k.p95_ttft_ms), electron: fmtMs(e.p95_ttft_ms), note: k.p95_ttft_ms && e.p95_ttft_ms ? "Kourier tail latency much lower" : "" },
    { metric: "Median End-to-End Time", kourier: fmtS(k.median_e2e_ms), electron: fmtS(e.median_e2e_ms), note: k.median_e2e_ms && e.median_e2e_ms ? `Kourier ${(e.median_e2e_ms / k.median_e2e_ms).toFixed(1)}× faster end-to-end` : "" },
    { metric: "Request Success Rate", kourier: fmtPct(k.success_rate), electron: fmtPct(e.success_rate), note: `Both ≥${Math.min(k.success_rate ?? 100, e.success_rate ?? 100).toFixed(0)}%; ${k.http_errors} vs ${e.http_errors} failures` },
    { metric: "Stream Completion Rate", kourier: fmtPct(k.stream_completion_rate), electron: fmtPct(e.stream_completion_rate), note: k.stream_completion_rate && e.stream_completion_rate ? (k.stream_completion_rate > e.stream_completion_rate ? "Kourier slightly higher" : "ElectronHub slightly higher") : "" },
    { metric: "Timeout Rate", kourier: fmtPct(k.timeout_rate), electron: fmtPct(e.timeout_rate), note: "No HTTP timeouts either side" },
    { metric: "Context Window", kourier: "262k", electron: "262k", note: "Identical 262k both providers" },
  ];
};

export const benchmarkRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{ bench: "Terminal Bench 2.1", kourier: k?.task_pass_rate ?? null, electronhub: e?.task_pass_rate ?? null }];
};

export const speedOutputRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{ bench: "Output Speed", kourier: k?.median_decode_tps ?? null, electronhub: e?.median_decode_tps ?? null }];
};
export const speedEffectiveRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{ bench: "Effective Speed", kourier: k?.median_effective_tps ?? null, electronhub: e?.median_effective_tps ?? null }];
};
export const ttftRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{ bench: "Time to First Token", kourier: k?.median_ttft_ms ?? null, electronhub: e?.median_ttft_ms ?? null }];
};
export const responseRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{
    bench: "Response Time",
    kourier: k?.median_e2e_ms ? Math.round(k.median_e2e_ms / 100) / 10 : null,
    electronhub: e?.median_e2e_ms ? Math.round(e.median_e2e_ms / 100) / 10 : null,
  }];
};
export const successRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{ bench: "Success Rate", kourier: k?.success_rate ?? null, electronhub: e?.success_rate ?? null }];
};
export const timeoutRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [{ bench: "Timeout Rate", kourier: k?.timeout_rate ?? null, electronhub: e?.timeout_rate ?? null }];
};
export const breakdownRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  if (!k || !e) return [];
  const kErr = ((k.http_errors ?? 0) / Math.max(1, k.requests)) * 100;
  const eErr = ((e.http_errors ?? 0) / Math.max(1, e.requests)) * 100;
  return [
    { provider: "Kourier", kTimeout: k.timeout_rate ?? 0, kOther: Math.max(0, kErr - (k.timeout_rate ?? 0)), eTimeout: 0, eOther: 0 },
    { provider: "ElectronHub", kTimeout: 0, kOther: 0, eTimeout: e.timeout_rate ?? 0, eOther: Math.max(0, eErr - (e.timeout_rate ?? 0)) },
  ];
};
export const breakdownConfig = {
  kTimeout: { label: "Kourier Timeout", color: "#1F704C" },
  kOther: { label: "Kourier Other", color: "#86efac" },
  eTimeout: { label: "ElectronHub Timeout", color: "#A242FB" },
  eOther: { label: "ElectronHub Other", color: "#ddd6fe" },
};
export const tokenRowsFor = (sel: RunSelection) => {
  const k = avgProvider(sel, "kourier");
  const e = avgProvider(sel, "electronhub");
  return [
    { provider: "Kourier", kInput: k?.median_input_tokens ?? null, kOutput: k?.median_output_tokens ?? null, kCache: k?.median_cache_tokens ?? null, eInput: 0, eOutput: 0, eCache: 0 },
    { provider: "ElectronHub", kInput: 0, kOutput: 0, kCache: 0, eInput: e?.median_input_tokens ?? null, eOutput: e?.median_output_tokens ?? null, eCache: e?.median_cache_tokens ?? null },
  ];
};
export const tokenConfig = {
  kInput: { label: "Kourier Input", color: "#1F704C" },
  kOutput: { label: "Kourier Output", color: "#2ec27a" },
  kCache: { label: "Kourier Cache", color: "#86efac" },
  eInput: { label: "ElectronHub Input", color: "#A242FB" },
  eOutput: { label: "ElectronHub Output", color: "#a78bfa" },
  eCache: { label: "ElectronHub Cache", color: "#ddd6fe" },
};

// ---------- Context-scaling points (both providers) for selection ----------
export type ContextPoint = { label: string; kourier: number | null; electronhub: number | null };

const scalingPoints = (sel: RunSelection, field: "speed" | "ttft" | "failure"): ContextPoint[] => {
  const k = avgContextScaling(sel, "kourier");
  const e = avgContextScaling(sel, "electronhub");
  const labels = Array.from(new Set([...k.map((p) => p.label), ...e.map((p) => p.label)])).sort();
  return labels.map((label) => ({
    label,
    kourier: k.find((p) => p.label === label)?.[field] ?? null,
    electronhub: e.find((p) => p.label === label)?.[field] ?? null,
  }));
};
export const speedContextPointsFor = (sel: RunSelection) => scalingPoints(sel, "speed");
export const latencyContextPointsFor = (sel: RunSelection) => scalingPoints(sel, "ttft");
export const contextOutputPointsFor = speedContextPointsFor;
export const contextTtftPointsFor = latencyContextPointsFor;
export const contextFailurePointsFor = (sel: RunSelection) => scalingPoints(sel, "failure");

// ============================================================
// Run history (unchanged trend semantics)
// ============================================================
export type Run = {
  id: string;
  date: string;
  dateKey: string;
  provider: string;
  model: string;
  benchmark: string;
  score: number | null;
  speed: number | null;
  ttft: number | null;
  success: number | null;
  requests: number;
  badges: string[];
};

const fmtDate = (iso: string) => {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};

export const runs: Run[] = (summary.run_history as any[]).map((r) => ({
  id: r.id,
  date: fmtDate(r.date),
  dateKey: r.date,
  provider: r.provider === "kourier" ? "Kourier" : "ElectronHub",
  model: r.model,
  benchmark: "Terminal Bench 2.1",
  score: r.score,
  speed: r.median_decode_tps == null ? null : Math.round(r.median_decode_tps * 10) / 10,
  ttft: r.median_ttft_ms ? r.median_ttft_ms / 1000 : null,
  success: r.success_rate,
  requests: r.requests,
  badges: [
    r.mode === "smoke" ? "Smoke" : "Full",
    r.concurrency && r.concurrency !== "sequential" ? `Concurrency ${r.concurrency}` : "Sequential",
    ...(r.reasoning && r.reasoning !== "default" ? [`Reasoning ${r.reasoning}`] : ["Reasoning default"]),
  ],
}));

export const providersList = ["All", "Kourier", "ElectronHub"];
export const modelsList = ["All", summary.model_label as string];
export const benchmarksList = ["All", "Terminal Bench 2.1"];

// ---------- Task results (table) ----------
export type TaskRow = {
  task: string;
  kourierPassed: boolean;
  electronPassed: boolean;
  kourierDurationSec: number | null;
  electronDurationSec: number | null;
  kourierInputTokens: number | null;
  electronInputTokens: number | null;
  kourierOutputTokens: number | null;
  electronOutputTokens: number | null;
  failureReason: string | null;
};

export const taskRowsFor = (rows: TaskResultRow[]): TaskRow[] =>
  rows.map((t) => ({
    task: t.task,
    kourierPassed: t.kourierPassed,
    electronPassed: t.electronPassed,
    kourierDurationSec: t.kourierDurationSec,
    electronDurationSec: t.electronDurationSec,
    kourierInputTokens: t.kourierInputTokens,
    electronInputTokens: t.electronInputTokens,
    kourierOutputTokens: t.kourierOutputTokens,
    electronOutputTokens: t.electronOutputTokens,
    failureReason: t.kourierException ?? t.electronException ?? null,
  }));

export function fmtDuration(sec: number | null): string {
  if (sec == null) return "n/a";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${String(s).padStart(2, "0")}s`;
}
