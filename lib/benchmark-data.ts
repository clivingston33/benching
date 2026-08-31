import summary from "@/data/benchmark-summary.json";

export type ProviderKey = "kourier" | "electronhub";

export const MODELS: Record<ProviderKey, string> = summary.models as Record<ProviderKey, string>;
export const PROVIDERS: ProviderKey[] = ["kourier", "electronhub"];

export const PROVIDER_LABEL: Record<ProviderKey, string> = {
  kourier: "Kourier",
  electronhub: "ElectronHub",
};

/** Real measured metrics from the canonical full runs (TB 2.1, 89 tasks). */
export type ProviderMetrics = {
  requests: number;
  success_rate: number | null;
  stream_completion_rate: number | null;
  timeout_rate: number | null;
  http_errors: number;
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

export const providers = summary.providers as Record<ProviderKey, ProviderMetrics>;

/** True when the provider has measured data for the metric (null = unavailable). */
export const has = (p: ProviderKey, v: number | null | undefined): v is number => v != null;

/** Series config for charts — only includes providers with the given data. */
export function seriesConfig(get: (p: ProviderKey) => number | null, base: Record<ProviderKey, { label: string; color: string }>) {
  const cfg: Record<string, { label: string; color: string }> = {};
  for (const p of PROVIDERS) {
    if (has(p, get(p))) cfg[p] = base[p];
  }
  return cfg;
}

export const providerConfig: Record<ProviderKey, { label: string; color: string }> = {
  kourier: { label: `qwen3.6-35b (Kourier)`, color: "#1F704C" },
  electronhub: { label: `glm-5.2:dev (ElectronHub)`, color: "#A242FB" },
};

export const KOURIER_NO_TELEMETRY =
  "Kourier's proxy recorded no token/usage telemetry — TTFT, decode speed, and token counts are unavailable for its 3,554 requests.";
export const MODEL_CONFOUND =
  "Data: legacy terminal-bench-results runs (Jul 25–30). Kourier ran qwen3.6-35b, ElectronHub ran glm-5.2:dev — different models per provider, so this is not a controlled provider comparison.";

// ---------- Comparison table ----------
export type ComparisonRow = { metric: string; kourier: string; electron: string; note: string };

const fmtMs = (v: number | null, unit = "ms") => (v == null ? "n/a" : `${Math.round(v).toLocaleString()} ${unit}`);
const fmtS = (v: number | null) => (v == null ? "n/a" : `${(v / 1000).toFixed(1)} s`);
const fmtPct = (v: number | null) => (v == null ? "n/a" : `${v.toFixed(1)}%`);
const fmtTps = (v: number | null) => (v == null ? "n/a" : `${Math.round(v)} tok/s`);

export const comparisonRows: ComparisonRow[] = [
  { metric: "Median Output Speed", kourier: fmtTps(providers.kourier.median_decode_tps), electron: fmtTps(providers.electronhub.median_decode_tps), note: "Kourier telemetry unavailable" },
  { metric: "Median Time to First Token", kourier: fmtMs(providers.kourier.median_ttft_ms), electron: fmtMs(providers.electronhub.median_ttft_ms), note: "Kourier telemetry unavailable" },
  { metric: "P95 Time to First Token", kourier: fmtMs(providers.kourier.p95_ttft_ms), electron: fmtMs(providers.electronhub.p95_ttft_ms), note: "Kourier telemetry unavailable" },
  { metric: "Median End-to-End Time", kourier: fmtS(providers.kourier.median_e2e_ms), electron: fmtS(providers.electronhub.median_e2e_ms), note: "Kourier ~54% slower end-to-end" },
  { metric: "Request Success Rate", kourier: fmtPct(providers.kourier.success_rate), electron: fmtPct(providers.electronhub.success_rate), note: "Kourier fewer failed requests" },
  { metric: "Stream Completion Rate", kourier: fmtPct(providers.kourier.stream_completion_rate), electron: fmtPct(providers.electronhub.stream_completion_rate), note: "Kourier proxy recorded no chunk data" },
  { metric: "Timeout Rate", kourier: fmtPct(providers.kourier.timeout_rate), electron: fmtPct(providers.electronhub.timeout_rate), note: "Kourier 19× HTTP 524" },
  { metric: "Context Window", kourier: "262k", electron: "262k", note: "Identical 262k both providers" },
];

// ---------- Benchmarks (task pass rate) ----------
export const benchmarkRows = [{ bench: "Terminal Bench 2.1", kourier: providers.kourier.task_pass_rate, electronhub: providers.electronhub.task_pass_rate }];

// ---------- Speed ----------
export const speedOutputRows = [{ bench: "Output Speed", kourier: providers.kourier.median_decode_tps, electronhub: providers.electronhub.median_decode_tps }];
export const speedEffectiveRows = [{ bench: "Effective Speed", kourier: providers.kourier.median_effective_tps, electronhub: providers.electronhub.median_effective_tps }];
export const speedContextPoints = summary.context_scaling.electronhub.speed.map((p) => ({ ctx: p.label, kourier: null as number | null, electronhub: p.electronhub }));

// ---------- Latency ----------
export const ttftRows = [{ bench: "Time to First Token", kourier: providers.kourier.median_ttft_ms, electronhub: providers.electronhub.median_ttft_ms }];
export const responseRows = [{ bench: "Response Time", kourier: providers.kourier.median_e2e_ms ? Math.round(providers.kourier.median_e2e_ms / 100) / 10 : null, electronhub: providers.electronhub.median_e2e_ms ? Math.round(providers.electronhub.median_e2e_ms / 100) / 10 : null }];
export const latencyContextPoints = summary.context_scaling.electronhub.ttft.map((p) => ({ ctx: p.label, kourier: null as number | null, electronhub: p.electronhub }));

// ---------- Reliability ----------
export const successRows = [{ bench: "Success Rate", kourier: providers.kourier.success_rate, electronhub: providers.electronhub.success_rate }];
export const timeoutRows = [{ bench: "Timeout Rate", kourier: providers.kourier.timeout_rate, electronhub: providers.electronhub.timeout_rate }];

// Failure breakdown: % of all requests that were timeouts vs other HTTP errors
export const breakdownRows = (() => {
  const k = providers.kourier;
  const e = providers.electronhub;
  return [
    { provider: "Kourier", kTimeout: k.timeout_rate ?? 0, kOther: (k.http_errors / k.requests) * 100 - (k.timeout_rate ?? 0), eTimeout: 0, eOther: 0 },
    { provider: "ElectronHub", kTimeout: 0, kOther: 0, eTimeout: e.timeout_rate ?? 0, eOther: (e.http_errors / e.requests) * 100 - (e.timeout_rate ?? 0) },
  ];
})();

export const breakdownConfig = {
  kTimeout: { label: "Kourier Timeout", color: "#1F704C" },
  kOther: { label: "Kourier Other", color: "#86efac" },
  eTimeout: { label: "ElectronHub Timeout", color: "#A242FB" },
  eOther: { label: "ElectronHub Other", color: "#ddd6fe" },
};

// ---------- Token use ----------
export const tokenRows = [
  { provider: "Kourier", kInput: null as number | null, kOutput: null as number | null, kCache: null as number | null, eInput: 0, eOutput: 0, eCache: 0 },
  { provider: "ElectronHub", kInput: 0, kOutput: 0, kCache: 0, eInput: providers.electronhub.median_input_tokens, eOutput: providers.electronhub.median_output_tokens, eCache: providers.electronhub.median_cache_tokens },
];

export const tokenConfig = {
  kInput: { label: "Kourier Input", color: "#1F704C" },
  kOutput: { label: "Kourier Output", color: "#2ec27a" },
  kCache: { label: "Kourier Cache", color: "#86efac" },
  eInput: { label: "ElectronHub Input", color: "#A242FB" },
  eOutput: { label: "ElectronHub Output", color: "#a78bfa" },
  eCache: { label: "ElectronHub Cache", color: "#ddd6fe" },
};

// ---------- Context scaling (electronhub-only) ----------
export const contextOutputPoints = summary.context_scaling.electronhub.speed.map((p) => ({ label: p.label, kourier: null as number | null, electronhub: p.electronhub }));
export const contextTtftPoints = summary.context_scaling.electronhub.ttft.map((p) => ({ label: p.label, kourier: null as number | null, electronhub: p.electronhub }));
export const contextFailurePoints = summary.context_scaling.electronhub.failure.map((p) => ({ label: p.label, kourier: null as number | null, electronhub: p.electronhub }));

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

export const runs: Run[] = summary.run_history
  .filter((r) => r.score != null || r.requests > 0)
  .map((r) => ({
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
      r.concurrency ? `Concurrency ${r.concurrency}` : "",
      r.attempts ? `Attempts ${r.attempts}` : "",
      r.max_retries ? `Retries ${r.max_retries}` : "",
      r.reasoning ? "Reasoning" : "",
    ].filter(Boolean),
  }));

export const providersList = ["All", "Kourier", "ElectronHub"];
export const modelsList = ["All", ...Array.from(new Set(runs.map((r) => r.model))).sort()];
export const benchmarksList = ["All", "Terminal Bench 2.1"];

// ---------- Task results ----------
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

export const ALL_TASKS: TaskRow[] = (summary.task_results as any[]).map((t) => ({
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
