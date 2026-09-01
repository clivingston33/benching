import summary from "@/data/benchmark-summary.json";

export type ProviderKey = string;

/** Provider names present in the comparison, in run order. */
export const PROVIDERS: ProviderKey[] = Object.keys(summary.providers);
export const MODEL_LABEL: string = summary.model_label as string;

const DISPLAY: Record<string, string> = { kourier: "Kourier", electronhub: "ElectronHub" };
export const PROVIDER_LABEL: Record<string, string> = Object.fromEntries(
  PROVIDERS.map((p) => [p, DISPLAY[p] ?? p[0].toUpperCase() + p.slice(1)])
);

/** Stable per-provider colors — kourier/electronhub keep brand colors, others get palette entries. */
const BRAND: Record<string, string> = { kourier: "#1F704C", electronhub: "#A242FB" };
const PALETTE = ["#0EA5E9", "#F59E0B", "#EF4444", "#14B8A6", "#8B5CF6", "#EAB308", "#EC4899", "#10B981", "#6366F1", "#F97316"];
const COLOR_INDEX: Record<string, number> = {};
let next = 0;
function colorFor(prov: string): string {
  if (BRAND[prov]) return BRAND[prov];
  if (!(prov in COLOR_INDEX)) COLOR_INDEX[prov] = next++;
  return PALETTE[COLOR_INDEX[prov] % PALETTE.length];
}

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
  task_pass_rate: number | null;
  tasks_passed: number;
  tasks_total: number;
};

export const providers = summary.providers as Record<string, ProviderMetrics>;

export const has = (p: string, v: number | null | undefined): v is number => v != null;

export const providerConfig: Record<string, { label: string; color: string }> = Object.fromEntries(
  PROVIDERS.map((p) => [p, { label: `${MODEL_LABEL} (${PROVIDER_LABEL[p]})`, color: colorFor(p) }])
);

export const APPLES_TO_APPLES = summary.source as string;

// ---------- Comparison table ----------
export type ComparisonRow = { metric: string; values: Record<string, string>; note: string };

const fmtMs = (v: number | null) => (v == null ? "n/a" : `${Math.round(v).toLocaleString()} ms`);
const fmtS = (v: number | null) => (v == null ? "n/a" : `${(v / 1000).toFixed(1)} s`);
const fmtPct = (v: number | null) => (v == null ? "n/a" : `${v.toFixed(1)}%`);
const fmtTps = (v: number | null) => (v == null ? "n/a" : `${Math.round(v)} tok/s`);
const fmtK = (v: number | null) => (v == null ? "n/a" : `${Math.round(v / 1000)}k`);

function row(metric: string, get: (p: ProviderMetrics) => number | null, fmt: (v: number | null) => string, note: string): ComparisonRow {
  return {
    metric,
    values: Object.fromEntries(PROVIDERS.map((p) => [p, fmt(get(providers[p]))])),
    note,
  };
}

export const comparisonRows: ComparisonRow[] = [
  row("Median Output Speed", (m) => m.median_decode_tps, fmtTps, "Median decode tokens/second"),
  row("Median Time to First Token", (m) => m.median_ttft_ms, fmtMs, "Median client-observed TTFT"),
  row("P95 Time to First Token", (m) => m.p95_ttft_ms, fmtMs, "Tail TTFT (95th percentile)"),
  row("Median End-to-End Time", (m) => m.median_e2e_ms, fmtS, "Median request duration"),
  row("Request Success Rate", (m) => m.success_rate, fmtPct, "HTTP 200 share of requests"),
  row("Stream Completion Rate", (m) => m.stream_completion_rate, fmtPct, "Streams that delivered content"),
  row("Timeout Rate", (m) => m.timeout_rate, fmtPct, "Requests that timed out"),
  row("Context Window", (m) => m.context_window ?? null, fmtK, "Configured context window"),
];

// ---------- Benchmarks ----------
export const benchmarkRows = [
  { bench: "Terminal Bench 2.1", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].task_pass_rate])) },
];

// ---------- Speed ----------
export const speedOutputRows = [
  { bench: "Output Speed", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].median_decode_tps])) },
];
export const speedEffectiveRows = [
  { bench: "Effective Speed", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].median_effective_tps])) },
];

type ContextPoint = { label: string; [provider: string]: number | null | string };

type ScalingEntry = { label: string; [provider: string]: number | null | string };

function scalingSeries(prov: string, key: "speed" | "ttft" | "failure"): ScalingEntry[] {
  const byProvider = (summary.context_scaling as Record<string, Record<string, ScalingEntry[]>>)[prov];
  return byProvider?.[key] ?? [];
}

function mergeScaling(key: "speed" | "ttft" | "failure"): ContextPoint[] {
  const labels = new Set<string>();
  for (const prov of PROVIDERS) {
    for (const pt of scalingSeries(prov, key)) labels.add(pt.label);
  }
  return Array.from(labels).sort().map((label) => {
    const point: ContextPoint = { label };
    for (const prov of PROVIDERS) {
      const value = scalingSeries(prov, key).find((x) => x.label === label)?.[prov];
      point[prov] = typeof value === "number" ? value : null;
    }
    return point;
  });
}

export const speedContextPoints = mergeScaling("speed");
export const latencyContextPoints = mergeScaling("ttft");

// ---------- Latency ----------
export const ttftRows = [
  { bench: "Time to First Token", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].median_ttft_ms])) },
];
export const responseRows = [
  { bench: "Response Time", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].median_e2e_ms ? Math.round(providers[p].median_e2e_ms! / 100) / 10 : null])) },
];

// ---------- Reliability ----------
export const successRows = [
  { bench: "Success Rate", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].success_rate])) },
];
export const timeoutRows = [
  { bench: "Timeout Rate", ...Object.fromEntries(PROVIDERS.map((p) => [p, providers[p].timeout_rate])) },
];

// Failure breakdown: % of all requests that failed (errors / requests)
export const breakdownRows = PROVIDERS.map((prov) => {
  const m = providers[prov];
  const err = ((m.http_errors ?? 0) / m.requests) * 100;
  const timeout = m.timeout_rate ?? 0;
  const other = Math.max(0, err - timeout);
  const row: Record<string, number | string> = { provider: PROVIDER_LABEL[prov] };
  for (const p2 of PROVIDERS) {
    row[`${p2}Timeout`] = p2 === prov ? timeout : 0;
    row[`${p2}Other`] = p2 === prov ? other : 0;
  }
  return row;
});

export const breakdownConfig: Record<string, { label: string; color: string }> = Object.fromEntries(
  PROVIDERS.flatMap((p) => [
    [`${p}Timeout`, { label: `${PROVIDER_LABEL[p]} Timeout`, color: colorFor(p) }],
    [`${p}Other`, { label: `${PROVIDER_LABEL[p]} Other`, color: lighten(colorFor(p)) }],
  ])
);

function lighten(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, ((n >> 16) & 255) + 90);
  const g = Math.min(255, ((n >> 8) & 255) + 90);
  const b = Math.min(255, (n & 255) + 90);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

// ---------- Token use ----------
export const tokenRows = PROVIDERS.map((prov) => {
  const m = providers[prov];
  const row: Record<string, number | string | null> = { provider: PROVIDER_LABEL[prov] };
  for (const p2 of PROVIDERS) {
    row[`${p2}Input`] = p2 === prov ? m.median_input_tokens : 0;
    row[`${p2}Output`] = p2 === prov ? m.median_output_tokens : 0;
    row[`${p2}Cache`] = p2 === prov ? m.median_cache_tokens : 0;
  }
  return row;
});

export const tokenConfig: Record<string, { label: string; color: string }> = Object.fromEntries(
  PROVIDERS.flatMap((p) => [
    [`${p}Input`, { label: `${PROVIDER_LABEL[p]} Input`, color: colorFor(p) }],
    [`${p}Output`, { label: `${PROVIDER_LABEL[p]} Output`, color: darken(colorFor(p)) }],
    [`${p}Cache`, { label: `${PROVIDER_LABEL[p]} Cache`, color: lighten(colorFor(p)) }],
  ])
);

function darken(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, ((n >> 16) & 255) - 40);
  const g = Math.max(0, ((n >> 8) & 255) - 40);
  const b = Math.max(0, (n & 255) - 40);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

// ---------- Context scaling ----------
export const contextOutputPoints = mergeScaling("speed");
export const contextTtftPoints = mergeScaling("ttft");
export const contextFailurePoints = mergeScaling("failure");

// ---------- Run history ----------
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

export const runs: Run[] = summary.run_history.map((r) => ({
  id: r.id,
  date: fmtDate(r.date),
  dateKey: r.date,
  provider: PROVIDER_LABEL[r.provider] ?? r.provider,
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

export const providersList = ["All", ...runs.map((r) => r.provider).filter((v, i, a) => a.indexOf(v) === i)];
export const modelsList = ["All", MODEL_LABEL];
export const benchmarksList = ["All", "Terminal Bench 2.1"];

// ---------- Task results ----------
export type TaskRow = {
  task: string;
  results: Record<string, { passed: boolean | null; durationSec: number | null; inputTokens: number | null; outputTokens: number | null }>;
  failureReason: string | null;
};

type TaskResultSummary = {
  task: string;
  [key: string]: string | boolean | number | null;
};

export const ALL_TASKS: TaskRow[] = (summary.task_results as TaskResultSummary[]).map((t) => {
  const results: TaskRow["results"] = {};
  let failureReason: string | null = null;
  for (const prov of PROVIDERS) {
    const passed = t[`${prov}Passed`];
    results[prov] = {
      passed: passed == null ? null : Boolean(passed),
      durationSec: typeof t[`${prov}DurationSec`] === "number" ? (t[`${prov}DurationSec`] as number) : null,
      inputTokens: typeof t[`${prov}InputTokens`] === "number" ? (t[`${prov}InputTokens`] as number) : null,
      outputTokens: typeof t[`${prov}OutputTokens`] === "number" ? (t[`${prov}OutputTokens`] as number) : null,
    };
    const exc = t[`${prov}Exception`];
    if (typeof exc === "string") failureReason = exc;
  }
  return { task: t.task, results, failureReason };
});

export function fmtDuration(sec: number | null): string {
  if (sec == null) return "n/a";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export const logoFor = (prov: string): string | null => {
  const known: Record<string, string> = { kourier: "/kourier.svg", electronhub: "/electron.svg" };
  return known[prov] ?? null;
};
