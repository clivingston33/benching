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
import { successRows, timeoutRows, breakdownRows, breakdownConfig, providerConfig, APPLES_TO_APPLES , PROVIDERS, PROVIDER_LABEL, logoFor } from "@/lib/benchmark-data";

type Tab = "success" | "timeout" | "breakdown";

const reliabilityConfig = providerConfig;

export default function ReliabilitySection() {
  const [tab, setTab] = useState<Tab>("success");
  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <button className={`bench-tab ${tab === "success" ? "active" : ""}`} onClick={() => setTab("success")}>
          Success Rate
        </button>
        <button className={`bench-tab ${tab === "timeout" ? "active" : ""}`} onClick={() => setTab("timeout")}>
          Timeout
        </button>
        <button className={`bench-tab ${tab === "breakdown" ? "active" : ""}`} onClick={() => setTab("breakdown")}>
          Failure Breakdown
        </button>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          {tab === "success" && "Success Rate"}
          {tab === "timeout" && "Timeout Rate"}
          {tab === "breakdown" && "Failure Breakdown"}
          <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">
          {tab === "success" ? "HTTP 200 share of all requests — Higher is better." : "Lower is better."}
        </p>
      </div>
      <div className="chart-wrap" style={{ height: tab === "breakdown" ? 360 : 340 }}>
        {tab === "success" && (
          <BarChart data={successRows} config={reliabilityConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            {PROVIDERS.map((p) => <Bar key={p} dataKey={p} />)}
            <BarLabels formatter={(v) => `${v.toFixed(1)}%`} offset={12} />
            <BarSeriesLogos logos={Object.fromEntries(PROVIDERS.map((p) => [p, logoFor(p)]).filter(([, v]) => v))} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v.toFixed(1)}%`} />
          </BarChart>
        )}
        {tab === "timeout" && (
          <BarChart data={timeoutRows} config={reliabilityConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            {PROVIDERS.map((p) => <Bar key={p} dataKey={p} />)}
            <BarLabels formatter={(v) => `${v.toFixed(2)}%`} offset={12} />
            <BarSeriesLogos logos={Object.fromEntries(PROVIDERS.map((p) => [p, logoFor(p)]).filter(([, v]) => v))} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v.toFixed(2)}%`} />
          </BarChart>
        )}
        {tab === "breakdown" && (
          <BarChart data={breakdownRows} config={breakdownConfig} stackType="stacked" className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="provider" />
            <YAxis tickCount={5} tickFormatter={(v) => `${v}%`} />
            {PROVIDERS.flatMap((p) => [<Bar key={`${p}Timeout`} dataKey={`${p}Timeout`} />, <Bar key={`${p}Other`} dataKey={`${p}Other`} />])}
            <BarLabels formatter={(v) => `${v.toFixed(1)}%`} offset={12} />
            <BarCategoryLogos categoryKey="provider" logos={Object.fromEntries(PROVIDERS.map((p) => [PROVIDER_LABEL[p], logoFor(p)]).filter(([, v]) => v))} />
            <Legend align="right" />
            <Tooltip labelKey="provider" valueFormatter={(v) => (v === 0 ? "" : `${v.toFixed(1)}%`)} />
          </BarChart>
        )}
      </div>

      <div className="bench-foot">
        {tab === "success" ? "Higher is better" : "Lower is better"} · {APPLES_TO_APPLES}
      </div>
    </div>
  );
}
