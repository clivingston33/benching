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
import { tokenRows, tokenConfig, APPLES_TO_APPLES , PROVIDERS, PROVIDER_LABEL, logoFor } from "@/lib/benchmark-data";

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
        <p className="bench-desc">Median reported tokens per request — Input / Output / Cache</p>
      </div>

      <div className="chart-wrap" style={{ height: 360 }}>
        <BarChart data={tokenRows} config={tokenConfig} stackType="stacked" className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 50 }}>
          <Grid horizontal />
          <XAxis dataKey="provider" />
          <YAxis tickCount={5} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
          {PROVIDERS.flatMap((p) => [<Bar key={`${p}Input`} dataKey={`${p}Input`} />, <Bar key={`${p}Output`} dataKey={`${p}Output`} />, <Bar key={`${p}Cache`} dataKey={`${p}Cache`} />])}
          <BarLabels formatter={(v) => (v ? `${Math.round(v / 1000)}k` : "")} offset={12} />
          <BarCategoryLogos categoryKey="provider" logos={Object.fromEntries(PROVIDERS.map((p) => [PROVIDER_LABEL[p], logoFor(p)]).filter(([, v]) => v))} />
          <Legend align="right" />
          <Tooltip labelKey="provider" valueFormatter={(v) => (v === 0 ? "" : `${Math.round(v).toLocaleString()}`)} />
        </BarChart>
      </div>

      <div className="bench-foot">Lower total is better · {APPLES_TO_APPLES}</div>
    </div>
  );
}
