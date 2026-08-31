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

type Tab = "success" | "timeout" | "breakdown";

const successRows = [{ bench: "Success Rate", kourier: 98.4, electronhub: 96.7 }];
const timeoutRows = [{ bench: "Timeout Rate", kourier: 1.1, electronhub: 2.8 }];
const breakdownRows = [
  { provider: "Kourier", kTimeout: 1.1, kOther: 0.5, eTimeout: 0, eOther: 0 },
  { provider: "ElectronHub", kTimeout: 0, kOther: 0, eTimeout: 2.8, eOther: 0.5 },
];
const breakdownConfig = {
  kTimeout: { label: "Kourier Timeout", color: "#1F704C" as const },
  kOther: { label: "Kourier Other", color: "#86efac" as const },
  eTimeout: { label: "ElectronHub Timeout", color: "#A242FB" as const },
  eOther: { label: "ElectronHub Other", color: "#ddd6fe" as const },
};
const reliabilityConfig = {
  kourier: { label: "DeepSeek V4 flash 0731 (Kourier)", color: "#1F704C" as const },
  electronhub: { label: "DeepSeek V4 flash 0731 (ElectronHub)", color: "#A242FB" as const },
};

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
          DeepSeek v4 flash 0731 · {tab === "success" ? "Higher is better." : "Lower is better."}
        </p>
      </div>
      <div className="chart-wrap" style={{ height: tab === "breakdown" ? 360 : 340 }}>
        {tab === "success" && (
          <BarChart data={successRows} config={reliabilityConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            <Bar dataKey="kourier" />
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${v.toFixed(1)}%`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v.toFixed(1)}%`} />
          </BarChart>
        )}
        {tab === "timeout" && (
          <BarChart data={timeoutRows} config={reliabilityConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            <Bar dataKey="kourier" />
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${v.toFixed(1)}%`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v.toFixed(1)}%`} />
          </BarChart>
        )}
        {tab === "breakdown" && (
          <BarChart data={breakdownRows} config={breakdownConfig} stackType="stacked" className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="provider" />
            <YAxis tickCount={5} tickFormatter={(v) => `${v}%`} />
            <Bar dataKey="kTimeout" />
            <Bar dataKey="kOther" />
            <Bar dataKey="eTimeout" />
            <Bar dataKey="eOther" />
            <BarLabels formatter={(v) => `${v.toFixed(1)}%`} offset={12} />
            <BarCategoryLogos categoryKey="provider" logos={{ Kourier: "/kourier.svg", ElectronHub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="provider" valueFormatter={(v) => (v === 0 ? "" : `${v.toFixed(1)}%`)} />
          </BarChart>
        )}
      </div>

      <div className="bench-foot">{tab === "success" ? "Higher is better" : "Lower is better"}</div>
    </div>
  );
}
