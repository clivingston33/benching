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
import {
  ttftRows,
  responseRows,
  latencyContextPoints,
  providerConfig,
  has,
  KOURIER_NO_TELEMETRY,
} from "@/lib/benchmark-data";
type Tab = "ttft" | "response" | "context";

const contextPoints = latencyContextPoints;
const latencyConfig = providerConfig;

export default function LatencySection() {
  const [tab, setTab] = useState<Tab>("ttft");
  const kourierHasData = tab === "context" ? false : has("kourier", tab === "ttft" ? ttftRows[0].kourier : responseRows[0].kourier);
  const config =
    tab === "context"
      ? { electronhub: providerConfig.electronhub }
      : kourierHasData
        ? providerConfig
        : { electronhub: providerConfig.electronhub };

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
          Latency by context length
        </button>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          {tab === "ttft" && "Time to First Token"}
          {tab === "response" && "Response Time"}
          {tab === "context" && "Latency by Context Length"}
          <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">
          {tab === "context"
            ? "Median TTFT vs input context length (ElectronHub only) — Lower is better."
            : "Median values — Lower is better."}
        </p>
      </div>
      <div className="chart-wrap" style={{ height: tab === "context" ? 360 : 340 }}>
        {tab === "ttft" && (
          <BarChart data={ttftRows} config={config} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            {kourierHasData && <Bar dataKey="kourier" />}
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${Math.round(v)}ms`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v} ms`} />
          </BarChart>
        )}
        {tab === "response" && (
          <BarChart data={responseRows} config={config} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            {kourierHasData && <Bar dataKey="kourier" />}
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${v.toFixed(1)}s`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v.toFixed(1)} s`} />
          </BarChart>
        )}
        {tab === "context" && (
          <LineChart data={contextPoints} config={config} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 52 }}>
            <Grid horizontal />
            <XAxis dataKey="ctx" />
            <YAxis tickCount={5} />
            <Crosshair />
            <Line dataKey="electronhub"><ActiveDot /></Line>
            <Legend align="right" />
            <Tooltip labelKey="ctx" valueFormatter={(v) => `${v} ms`} />
          </LineChart>
        )}
      </div>

      <div className="bench-foot">Lower is better · {KOURIER_NO_TELEMETRY}</div>
    </div>
  );
}
