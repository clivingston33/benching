"use client";

import { useMemo, useState } from "react";
import { LineChart } from "@/dither-kit/area-chart";
import { Line } from "@/dither-kit/Line";
import { ActiveDot } from "@/dither-kit/ActiveDot";
import { Crosshair } from "@/dither-kit/Crosshair";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { allRuns, formatDate, providers as availableProviders, type RunSummary } from "@/lib/benchmark-data";
import { presentationFor } from "@/lib/provider-presentation";

 type Metric = "Benchmark Score" | "Output Speed" | "Time to First Token" | "Success Rate";

function metricValue(run: RunSummary, metric: Metric) {
  if (metric === "Benchmark Score") return run.score.value == null ? null : run.score.value * 100;
  if (metric === "Output Speed") return run.speed.decode_tps.p50;
  if (metric === "Time to First Token") return run.latency.ttft_ms.p50;
  return run.reliability.request_success_rate == null ? null : run.reliability.request_success_rate * 100;
}

export default function RunHistorySection() {
  const [provider, setProvider] = useState("all");
  const [model, setModel] = useState("all");
  const [benchmark, setBenchmark] = useState("all");
  const [metric, setMetric] = useState<Metric>("Benchmark Score");
  const models = Array.from(new Set(allRuns.map((run) => run.model)));
  const benchmarks = Array.from(new Set(allRuns.map((run) => `${run.benchmark.name} ${run.benchmark.version}`)));
  const filtered = useMemo(() => allRuns.filter((run) => (provider === "all" || run.provider.id === provider) && (model === "all" || run.model === model) && (benchmark === "all" || `${run.benchmark.name} ${run.benchmark.version}` === benchmark)), [provider, model, benchmark]);
  const activeProviders = Array.from(new Map(filtered.map((run, index) => [run.provider.id, presentationFor(run.provider, index)])).values());
  const trendData = filtered.map((run) => ({ date: `${formatDate(run.created_at_utc)} · ${run.provider.name}`, [run.provider.id]: metricValue(run, metric) }));
  const config = Object.fromEntries(activeProviders.map((item) => [item.id, { label: item.name, color: item.color }]));
  const formatValue = (value: number | null, valueMetric: string = metric) => value == null ? "n/a" : valueMetric === "Time to First Token" ? `${value.toFixed(1)}ms` : valueMetric === "Output Speed" ? `${value.toFixed(1)} tok/s` : `${value.toFixed(1)}%`;

  return <div className="benchmarks-card">
    <div className="rh-filters"><div className="rh-selects">
      <Field label="Provider"><select value={provider} onChange={(event) => setProvider(event.target.value)}><option value="all">All</option>{availableProviders.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
      <Field label="Model"><select value={model} onChange={(event) => setModel(event.target.value)}><option value="all">All</option>{models.map((item) => <option key={item}>{item}</option>)}</select></Field>
      <Field label="Benchmark"><select value={benchmark} onChange={(event) => setBenchmark(event.target.value)}><option value="all">All</option>{benchmarks.map((item) => <option key={item}>{item}</option>)}</select></Field>
      <Field label="Metric"><select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}><option>Benchmark Score</option><option>Output Speed</option><option>Time to First Token</option><option>Success Rate</option></select></Field>
    </div></div>
    <div className="rh-trend"><div className="rh-trend-header"><span>Performance Over Time</span></div><div className="chart-wrap" style={{ height: 380 }}><LineChart data={trendData} config={config} className="h-full w-full" margins={{ top: 32, right: 16, bottom: 28, left: 56 }}><Grid horizontal /><XAxis dataKey="date" /><YAxis tickCount={5} tickFormatter={formatValue} /><Crosshair />{activeProviders.map((item) => <Line key={item.id} dataKey={item.id}><ActiveDot /></Line>)}<Legend align="right" /><Tooltip labelKey="date" valueFormatter={formatValue} /></LineChart></div></div>
    <div className="rh-table-wrap"><table className="rh-table"><thead><tr><th>Run</th><th>Date</th><th>Provider</th><th>Model</th><th>Benchmark Score</th><th>Output Speed</th><th>TTFT</th><th>Success</th><th>Config</th></tr></thead><tbody>{filtered.map((run, index) => { const item = presentationFor(run.provider, index); return <tr key={run.run_id}><td className="rh-model">{run.run_id}</td><td>{formatDate(run.created_at_utc)}</td><td><span className="rh-provider">{item.logo && <img src={item.logo} alt="" width={14} height={14} />}{item.name}</span></td><td className="rh-model">{run.model}</td><td>{formatValue(metricValue(run, "Benchmark Score"), "Benchmark Score")}</td><td>{formatValue(metricValue(run, "Output Speed"), "Output Speed")}</td><td>{formatValue(metricValue(run, "Time to First Token"), "Time to First Token")}</td><td>{formatValue(metricValue(run, "Success Rate"), "Success Rate")}</td><td><span className="rh-badges"><span className="rh-badge">{run.reasoning}</span><span className="rh-badge">Concurrency {run.execution.concurrency}</span><span className="rh-badge">Trials {run.execution.trials}</span></span></td></tr>; })}</tbody></table></div>
  </div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="rh-field"><div className="rh-field-label">{label}</div><div className="rh-select-wrap">{children}<span className="rh-chevron" aria-hidden>▾</span></div></div>; }
