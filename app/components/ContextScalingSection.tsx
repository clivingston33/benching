"use client";

import { useState } from "react";
import { LineChart } from "@/dither-kit/area-chart";
import { Line } from "@/dither-kit/Line";
import { ActiveDot } from "@/dither-kit/ActiveDot";
import { Crosshair } from "@/dither-kit/Crosshair";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
import { chartConfigFor, contextRowsFor, getComparison } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Tab = "speed" | "latency" | "reliability";

export default function ContextScalingSection() {
  const { selection } = useRunSelection();
  const [tab, setTab] = useState<Tab>("speed");
  const comparison = getComparison(selection);
  const providers = comparison.providers.map((run) => run.provider);
  const rows = contextRowsFor(selection, tab);
  const label = tab === "speed" ? "Output Speed" : tab === "latency" ? "Time to First Token" : "Failure Rate";
  const unit = tab === "speed" ? " tok/s" : "%";

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <button className={`bench-tab ${tab === "speed" ? "active" : ""}`} onClick={() => setTab("speed")}>Output Speed by Context Length</button>
        <button className={`bench-tab ${tab === "latency" ? "active" : ""}`} onClick={() => setTab("latency")}>Time to First Token by Context Length</button>
        <button className={`bench-tab ${tab === "reliability" ? "active" : ""}`} onClick={() => setTab("reliability")}>Failure Rate by Context Length</button>
      </div>
      <div className="benchmarks-header">
        <h3 className="bench-title">{label} by Context Length <span className="bench-arrow">↗</span></h3>
        <p className="bench-desc">Precomputed context metrics · {tab === "speed" ? "Higher" : "Lower"} is better · {comparison.label}</p>
      </div>
      <div className="chart-wrap" style={{ height: 360 }}>
        <LineChart data={rows} config={chartConfigFor(providers)} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 52 }}>
          <Grid horizontal /><XAxis dataKey="label" /><YAxis tickCount={5} /><Crosshair />
          {providers.map((provider) => <Line key={provider.id} dataKey={provider.id}><ActiveDot /></Line>)}
          <Legend align="right" /><Tooltip labelKey="label" valueFormatter={(value) => `${value}${unit}`} />
        </LineChart>
      </div>
      <div className="bench-foot">{tab === "speed" ? "Higher" : "Lower"} is better · {comparison.label}</div>
    </div>
  );
}
