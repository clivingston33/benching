"use client";

import { useState } from "react";
import { BarChart } from "@/dither-kit/bar-chart";
import { Bar } from "@/dither-kit/Bar";
import { BarLabels } from "@/dither-kit/BarLabels";
import { BarSeriesLogos } from "@/dither-kit/BarSeriesLogos";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { breakdownConfigFor, breakdownRowsFor, chartConfigFor, getComparison, metricRowsFor } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Tab = "success" | "timeout" | "breakdown";

export default function ReliabilitySection() {
  const { selection } = useRunSelection();
  const [tab, setTab] = useState<Tab>("success");
  const comparison = getComparison(selection);
  const providers = comparison.providers.map((run) => run.provider);
  const rows = metricRowsFor(selection, tab === "success" ? "successRate" : "timeoutRate");
  const breakdownRows = breakdownRowsFor(selection);
  const config = tab === "breakdown" ? breakdownConfigFor(selection) : chartConfigFor(providers);
  const logos = Object.fromEntries(providers.map((provider) => [provider.name, provider.logo ?? ""]));

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <button className={`bench-tab ${tab === "success" ? "active" : ""}`} onClick={() => setTab("success")}>Success Rate</button>
        <button className={`bench-tab ${tab === "timeout" ? "active" : ""}`} onClick={() => setTab("timeout")}>Timeout</button>
        <button className={`bench-tab ${tab === "breakdown" ? "active" : ""}`} onClick={() => setTab("breakdown")}>Failure Breakdown</button>
      </div>
      <div className="benchmarks-header">
        <h3 className="bench-title">{tab === "success" ? "Success Rate" : tab === "timeout" ? "Timeout Rate" : "Failure Breakdown"} <span className="bench-arrow">↗</span></h3>
        <p className="bench-desc">Precomputed reliability metrics · {tab === "success" ? "Higher" : "Lower"} is better · {comparison.label}</p>
      </div>
      <div className="chart-wrap" style={{ height: tab === "breakdown" ? 360 : 340 }}>
        <BarChart data={tab === "breakdown" ? breakdownRows : rows} config={config} stackType={tab === "breakdown" ? "stacked" : undefined} className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 40 }}>
          <Grid horizontal /><XAxis dataKey={tab === "breakdown" ? "provider" : "bench"} /><YAxis tickCount={5} />
          {tab === "breakdown" ? providers.flatMap((provider) => [
            <Bar key={`${provider.id}-timeout`} dataKey={`${provider.id}-timeout`} />,
            <Bar key={`${provider.id}-other`} dataKey={`${provider.id}-other`} />,
          ]) : providers.map((provider) => <Bar key={provider.id} dataKey={provider.id} />)}
          <BarLabels formatter={(value) => `${value.toFixed(1)}%`} offset={12} />
          {tab === "breakdown" ? <BarSeriesLogos logos={logos} /> : <BarSeriesLogos logos={Object.fromEntries(providers.map((provider) => [provider.id, provider.logo ?? ""]))} />}
          <Legend align="right" /><Tooltip labelKey={tab === "breakdown" ? "provider" : "bench"} valueFormatter={(value) => `${value.toFixed(1)}%`} />
        </BarChart>
      </div>
      <div className="bench-foot">{tab === "success" ? "Higher" : "Lower"} is better · {comparison.label}</div>
    </div>
  );
}
