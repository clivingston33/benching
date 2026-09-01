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

import { benchmarkRows, providerConfig, providers, APPLES_TO_APPLES , PROVIDERS, logoFor } from "@/lib/benchmark-data";

const terminalConfig = providerConfig;

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
        <p className="bench-desc">
          Task success rate (verifier reward = 1.0) · Higher is better · {providers.kourier.tasks_passed}/
          {providers.kourier.tasks_total} vs {providers.electronhub.tasks_passed}/{providers.electronhub.tasks_total} tasks
        </p>
      </div>

      <div className="chart-wrap" style={{ height: 340 }}>
        <BarChart data={benchmarkRows} config={terminalConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
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
      <div className="bench-foot">Terminal Bench 2.1 — Higher is better · {APPLES_TO_APPLES}</div>
    </div>
  );
}
