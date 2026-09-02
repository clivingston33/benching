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
  speedOutputRowsFor,
  speedEffectiveRowsFor,
  speedContextPointsFor,
  avgProvider,
  providerConfig,
} from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";
type Tab = "output" | "effective" | "context";

const speedConfig = providerConfig;

export default function SpeedSection() {
  const { selection, label } = useRunSelection();
  const [tab, setTab] = useState<Tab>("output");
  const outputRows = speedOutputRowsFor(selection);
  const effectiveRows = speedEffectiveRowsFor(selection);
  const contextPoints = speedContextPointsFor(selection);
  const k = avgProvider(selection, "kourier");
  const e = avgProvider(selection, "electronhub");

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
            ? "Decode TPS vs context length — Higher is better."
            : tab === "effective"
              ? "Effective tok/s incl. overhead — Higher is better."
              : "Median decode tokens per second — Higher is better."}
          {" · "}
          {label}
        </p>
      </div>

      <div className="chart-wrap" style={{ height: tab === "context" ? 360 : 340 }}>
        {tab === "output" && (
          <BarChart data={outputRows} config={speedConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            <Bar dataKey="kourier" />
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${Math.round(v)} tok/s`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v} tok/s`} />
          </BarChart>
        )}
        {tab === "effective" && (
          <BarChart data={effectiveRows} config={speedConfig} className="h-full w-full" margins={{ top: 52, right: 12, bottom: 36, left: 40 }}>
            <Grid horizontal />
            <XAxis dataKey="bench" />
            <YAxis tickCount={5} />
            <Bar dataKey="kourier" />
            <Bar dataKey="electronhub" />
            <BarLabels formatter={(v) => `${Math.round(v)} tok/s`} offset={12} />
            <BarSeriesLogos logos={{ kourier: "/kourier.svg", electronhub: "/electron.svg" }} />
            <Legend align="right" />
            <Tooltip labelKey="bench" valueFormatter={(v) => `${v} tok/s`} />
          </BarChart>
        )}
        {tab === "context" && (
          <LineChart data={contextPoints} config={speedConfig} className="h-full w-full" margins={{ top: 32, right: 12, bottom: 22, left: 40 }}>
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
      </div>

      <div className="bench-foot">
        {tab === "context"
          ? `Speed — Higher is better · kourier n=${k?.requests ?? 0}, electronhub n=${e?.requests ?? 0} requests`
          : `Speed (tok/s) — Higher is better · ${label}`}
      </div>
    </div>
  );
}
