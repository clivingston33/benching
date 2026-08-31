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

type Run = {
  id: string;
  date: string;
  dateKey: string;
  provider: string;
  model: string;
  benchmark: string;
  score: number;
  speed: number;
  ttft: number;
  success: number;
  badges: string[];
};

const runs: Run[] = [
  {
    id: "1",
    date: "Aug 30",
    dateKey: "2026-08-30",
    provider: "Kourier",
    model: "dsv4f 0731",
    benchmark: "Terminal Bench 2.1",
    score: 61.8,
    speed: 78,
    ttft: 0.42,
    success: 98.4,
    badges: ["Sequential", "Reasoning Default", "Concurrency 3"],
  },
  {
    id: "2",
    date: "Aug 30",
    dateKey: "2026-08-30",
    provider: "ElectronHub",
    model: "dsv4f 0731",
    benchmark: "Terminal Bench 2.1",
    score: 57.3,
    speed: 71,
    ttft: 0.61,
    success: 96.7,
    badges: ["Sequential", "Reasoning Default", "Concurrency 3"],
  },
  {
    id: "3",
    date: "Sep 02",
    dateKey: "2026-09-02",
    provider: "Kourier",
    model: "dsv4f 0731",
    benchmark: "Terminal Bench 2.1",
    score: 63.1,
    speed: 81,
    ttft: 0.39,
    success: 99.0,
    badges: ["Parallel", "Reasoning Enabled", "Concurrency 3"],
  },
  {
    id: "5",
    date: "Aug 20",
    dateKey: "2026-08-20",
    provider: "Kourier",
    model: "dsv4f 0731",
    benchmark: "Terminal Bench 2.1",
    score: 60.2,
    speed: 75,
    ttft: 0.45,
    success: 97.9,
    badges: ["Sequential", "Reasoning Default", "Concurrency 3"],
  },
  {
    id: "6",
    date: "Aug 25",
    dateKey: "2026-08-25",
    provider: "ElectronHub",
    model: "dsv4f 0731",
    benchmark: "Terminal Bench 2.1",
    score: 56.8,
    speed: 69,
    ttft: 0.58,
    success: 96.9,
    badges: ["Sequential", "Reasoning Default", "Concurrency 3"],
  },
];

const providers = ["All", "Kourier", "ElectronHub"];
const models = ["All", "dsv4f 0731"];
const benchmarks = ["All", "Terminal Bench 2.1"];

type Metric = "Benchmark Score" | "Output Speed" | "Time to First Token" | "Success Rate";

const metricKey: Record<Metric, keyof Pick<Run, "score" | "speed" | "ttft" | "success">> = {
  "Benchmark Score": "score",
  "Output Speed": "speed",
  "Time to First Token": "ttft",
  "Success Rate": "success",
};

const trendConfig = {
  kourier: { label: "DeepSeek V4 flash 0731 (Kourier)", color: "#1F704C" as const },
  electronhub: { label: "DeepSeek V4 flash 0731 (ElectronHub)", color: "#A242FB" as const },
};

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

  const trendData = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => a.dateKey.localeCompare(b.dateKey));
    const dates = Array.from(new Set(sorted.map((r) => r.dateKey))).sort();
    const dateLabel = new Map<string, string>();
    sorted.forEach((r) => dateLabel.set(r.dateKey, r.date));
    let lastK: number | null = null;
    let lastE: number | null = null;
    return dates.map((dk) => {
      const kRun = sorted.find((r) => r.dateKey === dk && r.provider === "Kourier");
      const eRun = sorted.find((r) => r.dateKey === dk && r.provider === "ElectronHub");
      if (kRun) lastK = kRun[key] as number;
      if (eRun) lastE = eRun[key] as number;
      return {
        date: dateLabel.get(dk) ?? dk,
        kourier: lastK ?? 0,
        electronhub: lastE ?? 0,
      };
    });
  }, [filtered, key]);

  const activeTrendConfig = useMemo(() => {
    if (provider === "Kourier") return { kourier: trendConfig.kourier } as unknown as typeof trendConfig;
    if (provider === "ElectronHub") return { electronhub: trendConfig.electronhub } as unknown as typeof trendConfig;
    return trendConfig;
  }, [provider]);

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
            {activeTrendConfig.kourier && <Line dataKey="kourier"><ActiveDot /></Line>}
            {activeTrendConfig.electronhub && <Line dataKey="electronhub"><ActiveDot /></Line>}
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
            {filtered.map((r) => (
              <tr key={r.id} className={selected.has(r.id) ? "selected" : ""}>
                <td>
                  <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
                </td>
                <td>{r.date}</td>
                <td>
                  <span className="rh-provider">
                    <img src={r.provider === "Kourier" ? "/kourier.svg" : "/electron.svg"} alt="" width={14} height={14} />
                    {r.provider}
                  </span>
                </td>
                <td className="rh-model">{r.model}</td>
                <td>{r.score.toFixed(1)}%</td>
                <td>{r.speed} tok/s</td>
                <td>{r.ttft.toFixed(2)}s</td>
                <td>{r.success.toFixed(1)}%</td>
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
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
