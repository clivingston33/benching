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
import {
  contextOutputPoints,
  contextTtftPoints,
  contextFailurePoints,
  providerConfig,
  APPLES_TO_APPLES,
  PROVIDERS,
} from "@/lib/benchmark-data";

type Tab = "speed" | "ttft" | "failure";

const outputPoints = contextOutputPoints;
const ttftPoints = contextTtftPoints;
const failurePoints = contextFailurePoints;

const contextConfig = providerConfig;

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
          ElectronHub full run — buckets by reported input tokens ·{" "}
          {tab === "failure" ? "Lower is better." : tab === "ttft" ? "TTFT — Lower is better." : "Higher is better."}
        </p>
      </div>

      <div className="chart-wrap" style={{ height: 360 }}>
        {tab === "speed" && (
          <LineChart data={outputPoints} config={contextConfig} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 44 }}>
            <Grid horizontal />
            <XAxis dataKey="label" />
            <YAxis tickCount={5} />
            <Crosshair />
            {PROVIDERS.map((p) => <Line key={p} dataKey={p}><ActiveDot /></Line>)}
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
            {PROVIDERS.map((p) => <Line key={p} dataKey={p}><ActiveDot /></Line>)}
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
            {PROVIDERS.map((p) => <Line key={p} dataKey={p}><ActiveDot /></Line>)}
            <Legend align="right" />
            <Tooltip labelKey="label" valueFormatter={(v) => `${v}%`} />
          </LineChart>
        )}
      </div>

      <div className="bench-foot">
        {tab === "failure" || tab === "ttft" ? "Lower is better" : "Higher is better"} · {APPLES_TO_APPLES}
      </div>
    </div>
  );
}
