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
import { chartConfigFor, getComparison, metricRowsFor } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

export default function BenchmarksSection() {
  const { selection } = useRunSelection();
  const comparison = getComparison(selection);
  const rows = metricRowsFor(selection, "score");
  const logos = Object.fromEntries(comparison.providers.map((run) => [run.provider.id, run.provider.logo ?? ""]));

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs"><span className="bench-tab active">{comparison.providers[0]?.benchmark.name ?? "Benchmark"}</span></div>
      <div className="benchmarks-header">
        <h3 className="bench-title">{comparison.providers[0]?.benchmark.name ?? "Benchmark"} <span className="bench-arrow">↗</span></h3>
        <p className="bench-desc">Task success rate · Higher is better · {comparison.label}</p>
      </div>
      <div className="chart-wrap" style={{ height: 340 }}>
        <BarChart data={rows} config={chartConfigFor(comparison.providers.map((run) => run.provider))} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
          <Grid horizontal />
          <XAxis dataKey="bench" />
          <YAxis tickCount={5} />
          {comparison.providers.map((run) => <Bar key={run.provider.id} dataKey={run.provider.id} />)}
          <BarLabels formatter={(value) => String(Math.round(value))} offset={12} />
          <BarSeriesLogos logos={logos} />
          <Legend align="right" />
          <Tooltip labelKey="bench" valueFormatter={(value) => `${value}`} />
        </BarChart>
      </div>
      <div className="bench-foot">Higher is better · {comparison.label}</div>
    </div>
  );
}
