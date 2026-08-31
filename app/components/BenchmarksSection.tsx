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

const terminalRows = [{ bench: "Terminal Bench 2.1", kourier: 63, electronhub: 55 }];
const terminalConfig = {
  kourier: { label: "DeepSeek V4 flash 0731 (Kourier)", color: "#1F704C" as const },
  electronhub: { label: "DeepSeek V4 flash 0731 (ElectronHub)", color: "#A242FB" as const },
};

export default function BenchmarksSection() {
  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <span className="bench-tab active">Terminal Bench 2.1</span>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          Terminal Bench 2.1 <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">DeepSeek v4 flash 0731 — Task success rate · Higher is better · Out of 100</p>
      </div>

      <div className="chart-wrap" style={{ height: 340 }}>
        <BarChart data={terminalRows} config={terminalConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
          <Grid horizontal />
          <XAxis dataKey="bench" />
          <YAxis tickCount={5} />
          <Bar dataKey="kourier" />
          <Bar dataKey="electronhub" />
          <BarLabels formatter={(v) => String(Math.round(v))} offset={12} />
          <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
          <Legend align="right" />
          <Tooltip labelKey="bench" valueFormatter={(v) => `${v}`} />
        </BarChart>
      </div>
      <div className="bench-foot">Terminal Bench 2.1 — Higher is better</div>
    </div>
  );
}
