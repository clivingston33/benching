"use client";

import { useState } from "react";
import { BarChart } from "@/dither-kit/bar-chart";
import { LineChart } from "@/dither-kit/area-chart";
import { Bar } from "@/dither-kit/Bar";
import { BarLabels } from "@/dither-kit/BarLabels";
import { BarSeriesLogos } from "@/dither-kit/BarSeriesLogos";
import { Line } from "@/dither-kit/Line";
import { ActiveDot } from "@/dither-kit/ActiveDot";
import { Crosshair } from "@/dither-kit/Crosshair";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { chartConfigFor, contextRowsFor, getComparison, metricRowsFor, seriesFor } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Tab = "output" | "effective" | "context";

export default function SpeedSection() {
  const { selection, dataset } = useRunSelection();
  const [tab, setTab] = useState<Tab>("output");
  const comparison = getComparison(dataset, selection);
  const series = seriesFor(comparison.runs);
  const metric = tab === "output" ? "decode_tps" : "effective_tps";
  const rows = metricRowsFor(dataset, selection, metric);
  const contextRows = contextRowsFor(dataset, selection, "speed");
  const logos = Object.fromEntries(series.map((item) => [item.key, item.logo ?? ""]));

  return <div className="benchmarks-card">
    <div className="benchmarks-tabs"><button className={`bench-tab ${tab === "output" ? "active" : ""}`} onClick={() => setTab("output")}>Output Speed</button><button className={`bench-tab ${tab === "effective" ? "active" : ""}`} onClick={() => setTab("effective")}>Effective Speed</button><button className={`bench-tab ${tab === "context" ? "active" : ""}`} onClick={() => setTab("context")}>Speed by context length</button></div>
    <div className="benchmarks-header"><h3 className="bench-title">{tab === "output" ? "Output Speed" : tab === "effective" ? "Effective Speed" : "Speed by Context Length"} <span className="bench-arrow">↗</span></h3><p className="bench-desc">Canonical speed metrics · Higher is better · {comparison.label}</p></div>
    <div className="chart-wrap" style={{ height: tab === "context" ? 360 : 340 }}>
      {tab !== "context" ? <BarChart data={rows} config={chartConfigFor(comparison.runs)} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}><Grid horizontal /><XAxis dataKey="bench" /><YAxis tickCount={5} />{series.map((item) => <Bar key={item.key} dataKey={item.key} />)}<BarLabels formatter={(value) => `${Math.round(value)} tok/s`} offset={12} /><BarSeriesLogos logos={logos} /><Legend align="right" /><Tooltip labelKey="bench" valueFormatter={(value) => `${value} tok/s`} /></BarChart> : <LineChart data={contextRows} config={chartConfigFor(comparison.runs)} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 40 }}><Grid horizontal /><XAxis dataKey="label" /><YAxis tickCount={5} /><Crosshair />{series.map((item) => <Line key={item.key} dataKey={item.key}><ActiveDot /></Line>)}<Legend align="right" /><Tooltip labelKey="label" valueFormatter={(value) => `${value} tok/s`} /></LineChart>}
    </div>
    <div className="bench-foot">Higher is better · {comparison.label}</div>
  </div>;
}
