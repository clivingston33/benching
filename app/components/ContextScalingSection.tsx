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

type Tab = "speed" | "ttft" | "failure";

const outputPoints = [
  { label: "1k", kourier: 78, electronhub: 71 },
  { label: "2k", kourier: 77, electronhub: 70 },
  { label: "4k", kourier: 76, electronhub: 69 },
  { label: "8k", kourier: 75, electronhub: 68 },
  { label: "16k", kourier: 72, electronhub: 65 },
  { label: "32k", kourier: 68, electronhub: 60 },
  { label: "64k", kourier: 60, electronhub: 53 },
  { label: "128k", kourier: 52, electronhub: 45 },
];
const ttftPoints = [
  { label: "1k", kourier: 420, electronhub: 610 },
  { label: "2k", kourier: 435, electronhub: 635 },
  { label: "4k", kourier: 455, electronhub: 675 },
  { label: "8k", kourier: 480, electronhub: 720 },
  { label: "16k", kourier: 540, electronhub: 830 },
  { label: "32k", kourier: 620, electronhub: 950 },
  { label: "64k", kourier: 750, electronhub: 1130 },
  { label: "128k", kourier: 900, electronhub: 1350 },
];
const failurePoints = [
  { label: "1k", kourier: 0.5, electronhub: 1.0 },
  { label: "2k", kourier: 0.7, electronhub: 1.3 },
  { label: "4k", kourier: 0.85, electronhub: 1.6 },
  { label: "8k", kourier: 1.0, electronhub: 2.0 },
  { label: "16k", kourier: 1.5, electronhub: 2.8 },
  { label: "32k", kourier: 2.2, electronhub: 4.0 },
  { label: "64k", kourier: 3.4, electronhub: 5.8 },
  { label: "128k", kourier: 5.0, electronhub: 8.0 },
];

const contextConfig = {
  kourier: { label: "DeepSeek V4 flash 0731 (Kourier)", color: "#1F704C" as const },
  electronhub: { label: "DeepSeek V4 flash 0731 (ElectronHub)", color: "#A242FB" as const },
};

export default function ContextScalingSection() {
  const [tab, setTab] = useState<Tab>("speed");

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <button className={`bench-tab ${tab === "speed" ? "active" : ""}`} onClick={() => setTab("speed")}>
          Output Speed by Context Length
        </button>
        <button className={`bench-tab ${tab === "ttft" ? "active" : ""}`} onClick={() => setTab("ttft")}>
          Time to First Token by Context Length
        </button>
        <button className={`bench-tab ${tab === "failure" ? "active" : ""}`} onClick={() => setTab("failure")}>
          Failure Rate by Context Length
        </button>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          {tab === "speed" && "Output Speed by Context Length"}
          {tab === "ttft" && "Time to First Token by Context Length"}
          {tab === "failure" && "Failure Rate by Context Length"}
          <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">
          DeepSeek v4 flash 0731 · {tab === "failure" ? "Lower is better." : tab === "ttft" ? "TTFT — Lower is better." : "Higher is better."}
        </p>
      </div>

      <div className="chart-wrap" style={{ height: 360 }}>
        {tab === "speed" && (
          <LineChart data={outputPoints} config={contextConfig} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 44 }}>
            <Grid horizontal />
            <XAxis dataKey="label" />
            <YAxis tickCount={5} />
            <Crosshair />
            <Line dataKey="kourier"><ActiveDot /></Line>
            <Line dataKey="electronhub"><ActiveDot /></Line>
            <Legend align="right" />
            <Tooltip labelKey="label" valueFormatter={(v) => `${v} tok/s`} />
          </LineChart>
        )}
        {tab === "ttft" && (
          <LineChart data={ttftPoints} config={contextConfig} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="label" />
            <YAxis tickCount={5} />
            <Crosshair />
            <Line dataKey="kourier"><ActiveDot /></Line>
            <Line dataKey="electronhub"><ActiveDot /></Line>
            <Legend align="right" />
            <Tooltip labelKey="label" valueFormatter={(v) => `${v} ms`} />
          </LineChart>
        )}
        {tab === "failure" && (
          <LineChart data={failurePoints} config={contextConfig} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 44 }}>
            <Grid horizontal />
            <XAxis dataKey="label" />
            <YAxis tickCount={5} />
            <Crosshair />
            <Line dataKey="kourier"><ActiveDot /></Line>
            <Line dataKey="electronhub"><ActiveDot /></Line>
            <Legend align="right" />
            <Tooltip labelKey="label" valueFormatter={(v) => `${v}%`} />
          </LineChart>
        )}
      </div>

      <div className="bench-foot">{tab === "failure" || tab === "ttft" ? "Lower is better" : "Higher is better"}</div>
    </div>
  );
}
