"use client";

import { BarChart } from "@/dither-kit/bar-chart";
import { Bar } from "@/dither-kit/Bar";
import { BarLabels } from "@/dither-kit/BarLabels";
import { BarCategoryLogos } from "@/dither-kit/BarCategoryLogos";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";

const tokenRows = [
  { provider: "Kourier", kInput: 850, kOutput: 620, kCache: 210, eInput: 0, eOutput: 0, eCache: 0 },
  { provider: "ElectronHub", kInput: 0, kOutput: 0, kCache: 0, eInput: 900, eOutput: 650, eCache: 180 },
];

const tokenConfig = {
  kInput: { label: "Kourier Input", color: "#1F704C" as const },
  kOutput: { label: "Kourier Output", color: "#2ec27a" as const },
  kCache: { label: "Kourier Cache", color: "#86efac" as const },
  eInput: { label: "ElectronHub Input", color: "#A242FB" as const },
  eOutput: { label: "ElectronHub Output", color: "#a78bfa" as const },
  eCache: { label: "ElectronHub Cache", color: "#ddd6fe" as const },
};

export default function TokenUseSection() {
  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <span className="bench-tab active">Token Use</span>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          Token Use <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">DeepSeek v4 flash 0731 — Input / Output / Cache per request · Lower total is better</p>
      </div>

      <div className="chart-wrap" style={{ height: 360 }}>
        <BarChart data={tokenRows} config={tokenConfig} stackType="stacked" className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 50 }}>
          <Grid horizontal />
          <XAxis dataKey="provider" />
          <YAxis tickCount={5} />
          <Bar dataKey="kInput" />
          <Bar dataKey="kOutput" />
          <Bar dataKey="kCache" />
          <Bar dataKey="eInput" />
          <Bar dataKey="eOutput" />
          <Bar dataKey="eCache" />
          <BarLabels formatter={(v) => String(Math.round(v))} offset={12} />
          <BarCategoryLogos categoryKey="provider" logos={{ Kourier: "/kourier.svg", ElectronHub: "/electron.svg" }} />
          <Legend align="right" />
          <Tooltip labelKey="provider" valueFormatter={(v, k) => (v === 0 ? "" : String(v))} />
        </BarChart>
      </div>

      <div className="bench-foot">Lower total is better</div>
    </div>
  );
}
