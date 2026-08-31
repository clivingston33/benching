"use client";

import { useState } from "react";
import { BarChart } from "@/dither-kit/bar-chart";
import { LineChart } from "@/dither-kit/area-chart";
import { Bar } from "@/dither-kit/Bar";
import { BarLabels } from "@/dither-kit/BarLabels";
import { BarSeriesLogos } from "@/dither-kit/BarSeriesLogos";
import { Line } from "@/dither-kit/Line";
import { ActiveDot } from "@/dither-kit/ActiveDot";
import { Crosshair } from "@/dither-kit/Crosshair";
import { Grid } from "@/dither-kit/Grid";
import { XAxis } from "@/dither-kit/XAxis";
import { YAxis } from "@/dither-kit/YAxis";
import { Tooltip } from "@/dither-kit/Tooltip";
import { Legend } from "@/dither-kit/Legend";
type Tab = "ttft" | "response" | "context";

const ttftRows = [{ bench: "Time to First Token", kourier: 420, electronhub: 610 }];
const responseRows = [{ bench: "Response Time", kourier: 9.2, electronhub: 10.4 }];
const contextPoints = [
  { ctx: "1k", kourier: 420, electronhub: 610 },
  { ctx: "2k", kourier: 435, electronhub: 635 },
  { ctx: "4k", kourier: 455, electronhub: 675 },
  { ctx: "8k", kourier: 480, electronhub: 720 },
  { ctx: "16k", kourier: 540, electronhub: 830 },
  { ctx: "32k", kourier: 620, electronhub: 950 },
  { ctx: "64k", kourier: 750, electronhub: 1130 },
  { ctx: "128k", kourier: 900, electronhub: 1350 },
];
const latencyConfig = {
  kourier: { label: "DeepSeek V4 flash 0731 (Kourier)", color: "#1F704C" as const },
  electronhub: { label: "DeepSeek V4 flash 0731 (ElectronHub)", color: "#A242FB" as const },
};

export default function LatencySection() {
  const [tab, setTab] = useState<Tab>("ttft");

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <button className={`bench-tab ${tab === "ttft" ? "active" : ""}`} onClick={() => setTab("ttft")}>
          Time to First Token
        </button>
        <button className={`bench-tab ${tab === "response" ? "active" : ""}`} onClick={() => setTab("response")}>
          Response Time
        </button>
        <button className={`bench-tab ${tab === "context" ? "active" : ""}`} onClick={() => setTab("context")}>
          Latency by Context Length
        </button>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          {tab === "ttft" && "Time to First Token"}
          {tab === "response" && "Response Time"}
          {tab === "context" && "Latency by Context Length"}
          <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">DeepSeek v4 flash 0731 · Lower is better.</p>
      </div>
      <div className="chart-wrap" style={{ height: tab === "context" ? 360 : 340 }}>
        {tab === "ttft" && (
          <BarChart data={ttftRows} config={latencyConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            <Bar dataKey="kourier" />
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${Math.round(v)}ms`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v} ms`} />
          </BarChart>
        )}
        {tab === "response" && (
          <BarChart data={responseRows} config={latencyConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            <Bar dataKey="kourier" />
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${v.toFixed(1)}s`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v.toFixed(1)} s`} />
          </BarChart>
        )}
        {tab === "context" && (
          <LineChart data={contextPoints} config={latencyConfig} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="ctx" />
            <YAxis tickCount={5} />
            <Crosshair />
            <Line dataKey="kourier"><ActiveDot /></Line>
            <Line dataKey="electronhub"><ActiveDot /></Line>
            <Legend align="right" />
            <Tooltip labelKey="ctx" valueFormatter={(v) => `${v} ms`} />
          </LineChart>
        )}
      </div>

      <div className="bench-foot">Lower is better</div>
    </div>
  );
}
