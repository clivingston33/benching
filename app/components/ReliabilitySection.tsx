"use client";

import { useState } from "react";
import { BarChart } from "@/dither-kit/bar-chart";
import { Bar } from "@/dither-kit/Bar";
import { BarLabels } from "@/dither-kit/BarLabels";
import { BarSeriesLogos } from "@/dither-kit/BarSeriesLogos";
import { BarCategoryLogos } from "@/dither-kit/BarCategoryLogos";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { breakdownConfigFor, breakdownRowsFor, chartConfigFor, getComparison, metricRowsFor, seriesFor } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Tab = "success" | "timeout" | "breakdown";

export default function ReliabilitySection() {
  const { selection, dataset } = useRunSelection();
  const [tab, setTab] = useState<Tab>("success");
  const comparison = getComparison(dataset, selection);
  const series = seriesFor(comparison.runs);
  const rows = metricRowsFor(dataset, selection, tab === "success" ? "request_success_rate" : "timeout_rate");
  const breakdownRows = breakdownRowsFor(dataset, selection);
  const logos = Object.fromEntries(series.map((item) => [item.label, item.logo ?? ""]));

  return <div className="benchmarks-card">
    <div className="benchmarks-tabs"><button className={`bench-tab ${tab === "success" ? "active" : ""}`} onClick={() => setTab("success")}>Success Rate</button><button className={`bench-tab ${tab === "timeout" ? "active" : ""}`} onClick={() => setTab("timeout")}>Timeout</button><button className={`bench-tab ${tab === "breakdown" ? "active" : ""}`} onClick={() => setTab("breakdown")}>Failure Breakdown</button></div>
    <div className="benchmarks-header"><h3 className="bench-title">{tab === "success" ? "Success Rate" : tab === "timeout" ? "Timeout Rate" : "Failure Breakdown"} <span className="bench-arrow">↗</span></h3><p className="bench-desc">Canonical reliability metrics · {tab === "success" ? "Higher" : "Lower"} is better · {comparison.label}</p></div>
    <div className="chart-wrap" style={{ height: tab === "breakdown" ? 360 : 340 }}><BarChart data={tab === "breakdown" ? breakdownRows : rows} config={tab === "breakdown" ? breakdownConfigFor(dataset, selection) : chartConfigFor(comparison.runs)} stackType={tab === "breakdown" ? "stacked" : undefined} className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 40 }}><Grid horizontal /><XAxis dataKey={tab === "breakdown" ? "provider" : "bench"} /><YAxis tickCount={5} />{tab === "breakdown" ? series.flatMap((item) => [<Bar key={`${item.key}-timeout`} dataKey={`${item.key}-timeout`} />, <Bar key={`${item.key}-errors`} dataKey={`${item.key}-errors`} />]) : series.map((item) => <Bar key={item.key} dataKey={item.key} />)}<BarLabels formatter={(value) => `${value.toFixed(2)}%`} offset={12} />{tab === "breakdown" ? <BarCategoryLogos categoryKey="provider" logos={logos} /> : <BarSeriesLogos logos={Object.fromEntries(series.map((item) => [item.key, item.logo ?? ""]))} />}<Legend align="right" /><Tooltip labelKey={tab === "breakdown" ? "provider" : "bench"} valueFormatter={(value) => `${value.toFixed(2)}%`} /></BarChart></div>
    <div className="bench-foot">{tab === "success" ? "Higher" : "Lower"} is better · {comparison.label}</div>
  </div>;
}
