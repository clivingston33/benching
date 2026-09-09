"use client";

import { BarChart } from "@/dither-kit/bar-chart";
import { Bar } from "@/dither-kit/Bar";
import { BarLabels } from "@/dither-kit/BarLabels";
import { BarSeriesLogos } from "@/dither-kit/BarSeriesLogos";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { chartConfigFor, getComparison, metricRowsFor, seriesFor } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

export default function BenchmarksSection() {
  const { selection, dataset } = useRunSelection();
  const comparison = getComparison(dataset, selection);
  const series = seriesFor(comparison.runs);
  const rows = metricRowsFor(dataset, selection, "score");
  const logos = Object.fromEntries(series.map((item) => [item.key, item.logo ?? ""]));

  return <div className="benchmarks-card">
    <div className="benchmarks-tabs"><span className="bench-tab active">{comparison.source.benchmark.name} {comparison.source.benchmark.version}</span></div>
    <div className="benchmarks-header"><h3 className="bench-title">{comparison.source.benchmark.name} {comparison.source.benchmark.version} <span className="bench-arrow">↗</span></h3><p className="bench-desc">Task success rate · Higher is better · {comparison.label}</p></div>
    <div className="chart-wrap" style={{ height: 340 }}><BarChart data={rows} config={chartConfigFor(comparison.runs)} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}><Grid horizontal /><XAxis dataKey="bench" /><YAxis tickCount={5} />{series.map((item) => <Bar key={item.key} dataKey={item.key} />)}<BarLabels formatter={(value) => String(Math.round(value))} offset={12} /><BarSeriesLogos logos={logos} /><Legend align="right" /><Tooltip labelKey="bench" valueFormatter={(value) => `${value}%`} /></BarChart></div>
    <div className="bench-foot">Higher is better · {comparison.label}</div>
  </div>;
}
