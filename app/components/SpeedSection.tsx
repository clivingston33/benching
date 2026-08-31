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
  speedOutputRows,
  speedEffectiveRows,
  speedContextPoints,
  providerConfig,
  has,
  KOURIER_NO_TELEMETRY,
  providers,
} from "@/lib/benchmark-data";
type Tab = "output" | "effective" | "context";

const outputRows = speedOutputRows;
const effectiveRows = speedEffectiveRows;
const contextPoints = speedContextPoints;

const speedConfig = providerConfig;

export default function SpeedSection() {
  const [tab, setTab] = useState<Tab>("output");
  const kourierHasData = tab === "context" ? false : has("kourier", outputRows[0].kourier);
  const config =
    tab === "context"
      ? { electronhub: providerConfig.electronhub }
      : kourierHasData
        ? providerConfig
        : { electronhub: providerConfig.electronhub };

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-tabs">
        <button className={`bench-tab ${tab === "output" ? "active" : ""}`} onClick={() => setTab("output")}>
          Output Speed
        </button>
        <button className={`bench-tab ${tab === "effective" ? "active" : ""}`} onClick={() => setTab("effective")}>
          Effective Speed
        </button>
        <button className={`bench-tab ${tab === "context" ? "active" : ""}`} onClick={() => setTab("context")}>
          Speed by context length
        </button>
      </div>

      <div className="benchmarks-header">
        <h3 className="bench-title">
          {tab === "output" && "Output Speed"}
          {tab === "effective" && "Effective Speed"}
          {tab === "context" && "Decode TPS by Context Length"}
          <span className="bench-arrow">↗</span>
        </h3>
        <p className="bench-desc">
          {tab === "context"
            ? "Decode TPS vs context length (ElectronHub only — input tokens) — Higher is better."
            : tab === "effective"
              ? "Effective tok/s incl. overhead — Higher is better."
              : "Median decode tokens per second — Higher is better."}
        </p>
      </div>

      <div className="chart-wrap" style={{ height: tab === "context" ? 360 : 340 }}>
        {tab === "output" && (
          <BarChart data={outputRows} config={config} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            {kourierHasData && <Bar dataKey="kourier" />}
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${Math.round(v)} tok/s`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v} tok/s`} />
          </BarChart>
        )}
        {tab === "effective" && (
          <BarChart data={effectiveRows} config={config} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            {kourierHasData && <Bar dataKey="kourier" />}
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${Math.round(v)} tok/s`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v} tok/s`} />
          </BarChart>
        )}
        {tab === "context" && (
          <LineChart data={contextPoints} config={config} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="ctx" />
            <YAxis tickCount={5} />
            <Crosshair />
            <Line dataKey="electronhub"><ActiveDot /></Line>
            <Legend align="right" />
            <Tooltip labelKey="ctx" valueFormatter={(v) => `${v} tok/s`} />
          </LineChart>
        )}
      </div>

      <div className="bench-foot">
        {tab === "context"
          ? `Speed — Higher is better · ElectronHub n=${providers.electronhub.requests} requests`
          : `Speed (tok/s) — Higher is better · ${KOURIER_NO_TELEMETRY}`}
      </div>
    </div>
  );
}
