"use client";

import { useState, useMemo } from "react";
import { LineChart } from "@/dither-kit/area-chart";
import { Line } from "@/dither-kit/Line";
import { ActiveDot } from "@/dither-kit/ActiveDot";
import { Crosshair } from "@/dither-kit/Crosshair";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { runs, providersList, modelsList, benchmarksList, providerConfig, logoFor, PROVIDERS, PROVIDER_LABEL } from "@/lib/benchmark-data";
import type { Run } from "@/lib/benchmark-data";

const providers = providersList;
const models = modelsList;
const benchmarks = benchmarksList;

type Metric = "Benchmark Score" | "Output Speed" | "Time to First Token" | "Success Rate";

const metricKey: Record<Metric, keyof Pick<Run, "score" | "speed" | "ttft" | "success">> = {
  "Benchmark Score": "score",
  "Output Speed": "speed",
  "Time to First Token": "ttft",
  "Success Rate": "success",
};

const trendConfig = providerConfig;

export default function RunHistorySection() {
  const [provider, setProvider] = useState("All");
  const [model, setModel] = useState("All");
  const [benchmark, setBenchmark] = useState("All");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [metric, setMetric] = useState<Metric>("Benchmark Score");

  const filtered = useMemo(
    () =>
      runs.filter(
        (r) =>
          (provider === "All" || r.provider === provider) &&
          (model === "All" || r.model === model) &&
          (benchmark === "All" || r.benchmark === benchmark)
      ),
    [provider, model, benchmark]
  );

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedRuns = runs.filter((r) => selected.has(r.id));
  const canCompare = selectedRuns.length >= 2;
  const configsDiffer =
    canCompare && new Set(selectedRuns.map((r) => r.badges.join("|"))).size > 1;

  const key = metricKey[metric];

  // Providers present in the filtered runs (display names)
  const activeProviders = useMemo(() => {
    const set = new Set(filtered.map((r) => r.provider));
    return Array.from(set);
  }, [filtered]);

  const trendData = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => a.dateKey.localeCompare(b.dateKey));
    const dates = Array.from(new Set(sorted.map((r) => r.dateKey))).sort();
    const dateLabel = new Map<string, string>();
    sorted.forEach((r) => dateLabel.set(r.dateKey, r.date));
    const last = new Map<string, number | null>();
    activeProviders.forEach((p) => last.set(p, null));
    return dates.map((dk) => {
      const point: Record<string, string | number> = { date: dateLabel.get(dk) ?? dk };
      for (const prov of activeProviders) {
        const run = sorted.find((r) => r.dateKey === dk && r.provider === prov);
        if (run && run[key] != null) last.set(prov, run[key] as number);
        point[prov] = last.get(prov) ?? 0;
      }
      return point;
    });
  }, [filtered, key, activeProviders]);

  const activeTrendConfig = useMemo(() => {
    const cfg: Record<string, { label: string; color: string }> = {};
    for (const prov of activeProviders) {
      const hasData = filtered.some((r) => r.provider === prov && r[key] != null);
      if (hasData) {
        const rawKey = PROVIDERS.find((p) => PROVIDER_LABEL[p] === prov) ?? prov.toLowerCase();
        cfg[prov] = trendConfig[rawKey] ?? { label: prov, color: "#888" };
      }
    }
    return cfg;
  }, [activeProviders, filtered, key]);

  const yFmt = (v: number) => {
    if (metric === "Time to First Token") return `${v.toFixed(2)}s`;
    if (metric === "Benchmark Score" || metric === "Success Rate") return `${v}%`;
    return `${v}`;
  };
  const tipFmt = (v: number) => yFmt(v);

  return (
    <div className="benchmarks-card">
      <div className="rh-filters">
        <div className="rh-selects">
          <div className="rh-field">
            <div className="rh-field-label">Provider</div>
            <div className="rh-select-wrap">
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                {providers.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
              <span className="rh-chevron" aria-hidden>▾</span>
            </div>
          </div>
          <div className="rh-field">
            <div className="rh-field-label">Model</div>
            <div className="rh-select-wrap">
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                {models.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
              <span className="rh-chevron" aria-hidden>▾</span>
            </div>
          </div>
          <div className="rh-field">
            <div className="rh-field-label">Benchmark</div>
            <div className="rh-select-wrap">
              <select value={benchmark} onChange={(e) => setBenchmark(e.target.value)}>
                {benchmarks.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
              <span className="rh-chevron" aria-hidden>▾</span>
            </div>
          </div>
          <div className="rh-field">
            <div className="rh-field-label">Metric</div>
            <div className="rh-select-wrap">
              <select value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
                <option>Benchmark Score</option>
                <option>Output Speed</option>
                <option>Time to First Token</option>
                <option>Success Rate</option>
              </select>
              <span className="rh-chevron" aria-hidden>▾</span>
            </div>
          </div>
        </div>
        <button className={`rh-compare ${canCompare ? "" : "disabled"}`} disabled={!canCompare}>
          Compare selected {selected.size > 0 ? `(${selected.size})` : ""}
        </button>
      </div>

      {configsDiffer && canCompare && (
        <div className="rh-warning">
          Analyzer refuses to compare — selected runs differ in benchmark configuration, reasoning mode, or concurrency. Badges highlight differences.
        </div>
      )}

      <div className="rh-trend">
        <div className="rh-trend-header">
          <span>Performance Over Time</span>
        </div>
        <div className="chart-wrap" style={{ height: 380 }}>
          <LineChart data={trendData} config={activeTrendConfig} className="h-full w-full" margins={{ top: 32, right: 16, bottom: 28, left: 56 }}>
            <Grid horizontal />
            <XAxis dataKey="date" />
            <YAxis tickCount={5} tickFormatter={yFmt} />
            <Crosshair />
            {activeProviders.map((prov) => (
              <Line key={prov} dataKey={prov}><ActiveDot /></Line>
            ))}
            <Legend align="right" />
            <Tooltip labelKey="date" valueFormatter={tipFmt} />
          </LineChart>
        </div>
      </div>

      <div className="rh-table-wrap">
        <table className="rh-table">
          <thead>
            <tr>
              <th></th>
              <th>Date</th>
              <th>Provider</th>
              <th>Model</th>
              <th>Benchmark Score</th>
              <th>Output Speed</th>
              <th>TTFT</th>
              <th>Success</th>
              <th>Config</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const rawKey = PROVIDERS.find((p) => PROVIDER_LABEL[p] === r.provider) ?? r.provider.toLowerCase();
              const src = logoFor(rawKey);
              return (
                <tr key={r.id} className={selected.has(r.id) ? "selected" : ""}>
                  <td>
                    <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                  </td>
                  <td>{r.date}</td>
                  <td>
                    <span className="rh-provider">
                      {src ? <img src={src} alt="" width={14} height={14} /> : <span className="rh-provider-dot" />}
                      {r.provider}
                    </span>
                  </td>
                  <td className="rh-model">{r.model}</td>
                  <td>{r.score == null ? "n/a" : `${r.score.toFixed(1)}%`}</td>
                  <td>{r.speed == null ? "n/a" : `${r.speed} tok/s`}</td>
                  <td>{r.ttft == null ? "n/a" : `${r.ttft.toFixed(2)}s`}</td>
                  <td>{r.success == null ? "n/a" : `${r.success.toFixed(1)}%`}</td>
                  <td>
                    <span className="rh-badges">
                      {r.badges.map((b) => (
                        <span key={b} className="rh-badge">
                          {b}
                        </span>
                      ))}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
