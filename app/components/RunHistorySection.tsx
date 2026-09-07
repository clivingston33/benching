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
import { allRuns, providers, type RunSummary } from "@/lib/benchmark-data";

type Metric = "Benchmark Score" | "Output Speed" | "Time to First Token" | "Success Rate";
const metricValue = (run: RunSummary, metric: Metric) => {
  if (metric === "Benchmark Score") return run.score.value;
  if (metric === "Output Speed") return run.speed.outputTokensPerSecond;
  if (metric === "Time to First Token") return run.latency.ttftMs;
  return run.reliability.successRate;
};

export default function RunHistorySection() {
  const [provider, setProvider] = useState("all");
  const [model, setModel] = useState("all");
  const [benchmark, setBenchmark] = useState("all");
  const [metric, setMetric] = useState<Metric>("Benchmark Score");
  const models = Array.from(new Set(allRuns.map((run) => run.model)));
  const benchmarks = Array.from(new Set(allRuns.map((run) => run.benchmark.name)));
  const filtered = useMemo(() => allRuns.filter((run) =>
    (provider === "all" || run.provider.id === provider) &&
    (model === "all" || run.model === model) &&
    (benchmark === "all" || run.benchmark.name === benchmark)
  ), [provider, model, benchmark]);
  const trendData = useMemo(() => Array.from(new Set(filtered.map((run) => run.date))).sort().map((date) => ({
    date,
    ...Object.fromEntries(providers.map((item) => {
      const run = filtered.find((candidate) => candidate.date === date && candidate.provider.id === item.id);
      return [item.id, run ? metricValue(run, metric) : null];
    })),
  })), [filtered, metric]);
  const activeProviders = providers.filter((item) => provider === "all" || item.id === provider);
  const config = Object.fromEntries(activeProviders.map((item) => [item.id, { label: item.name, color: item.color }]));
  const formatValue = (value: number | null) => value == null ? "n/a" : metric === "Time to First Token" ? `${value.toFixed(1)}ms` : metric === "Output Speed" ? `${value.toFixed(1)} tok/s` : `${value.toFixed(1)}%`;

  return (
    <div className="benchmarks-card">
      <div className="rh-filters">
        <div className="rh-selects">
          <div className="rh-field"><div className="rh-field-label">Provider</div><div className="rh-select-wrap"><select value={provider} onChange={(event) => setProvider(event.target.value)}><option value="all">All</option>{providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><span className="rh-chevron" aria-hidden>▾</span></div></div>
          <div className="rh-field"><div className="rh-field-label">Model</div><div className="rh-select-wrap"><select value={model} onChange={(event) => setModel(event.target.value)}><option value="all">All</option>{models.map((item) => <option key={item}>{item}</option>)}</select><span className="rh-chevron" aria-hidden>▾</span></div></div>
          <div className="rh-field"><div className="rh-field-label">Benchmark</div><div className="rh-select-wrap"><select value={benchmark} onChange={(event) => setBenchmark(event.target.value)}><option value="all">All</option>{benchmarks.map((item) => <option key={item}>{item}</option>)}</select><span className="rh-chevron" aria-hidden>▾</span></div></div>
          <div className="rh-field"><div className="rh-field-label">Metric</div><div className="rh-select-wrap"><select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}><option>Benchmark Score</option><option>Output Speed</option><option>Time to First Token</option><option>Success Rate</option></select><span className="rh-chevron" aria-hidden>▾</span></div></div>
        </div>
      </div>
      <div className="rh-trend">
        <div className="rh-trend-header"><span>Performance Over Time</span></div>
        <div className="chart-wrap" style={{ height: 380 }}>
          <LineChart data={trendData} config={config} className="h-full w-full" margins={{ top: 32, right: 16, bottom: 28, left: 56 }}>
            <Grid horizontal /><XAxis dataKey="date" /><YAxis tickCount={5} tickFormatter={formatValue} /><Crosshair />
            {activeProviders.map((item) => <Line key={item.id} dataKey={item.id}><ActiveDot /></Line>)}
            <Legend align="right" /><Tooltip labelKey="date" valueFormatter={formatValue} />
          </LineChart>
        </div>
      </div>
      <div className="rh-table-wrap">
        <table className="rh-table">
          <thead><tr><th>Date</th><th>Provider</th><th>Model</th><th>Benchmark Score</th><th>Output Speed</th><th>TTFT</th><th>Success</th><th>Config</th></tr></thead>
          <tbody>{filtered.map((run) => <tr key={run.runId}>
            <td>{run.date}</td>
            <td><span className="rh-provider"><img src={run.provider.logo} alt="" width={14} height={14} />{run.provider.name}</span></td>
            <td className="rh-model">{run.model}</td>
            <td>{formatValue(run.score.value)}</td>
            <td>{run.speed.outputTokensPerSecond == null ? "n/a" : `${run.speed.outputTokensPerSecond.toFixed(1)} tok/s`}</td>
            <td>{run.latency.ttftMs == null ? "n/a" : `${run.latency.ttftMs.toFixed(1)}ms`}</td>
            <td>{run.reliability.successRate == null ? "n/a" : `${run.reliability.successRate.toFixed(1)}%`}</td>
            <td><span className="rh-badges">{run.badges.map((badge) => <span key={badge} className="rh-badge">{badge}</span>)}</span></td>
          </tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
