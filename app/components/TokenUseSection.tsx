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
import { getComparison, tokenConfigFor, tokenRowsFor } from "@/lib/benchmark-data";
import { presentationFor } from "@/lib/provider-presentation";
import { useRunSelection } from "@/lib/run-selection";

export default function TokenUseSection() {
  const { selection } = useRunSelection();
  const comparison = getComparison(selection);
  const rows = tokenRowsFor(selection);
  const providers = comparison.runs.map((run, index) => presentationFor(run.provider, index));
  const keys = providers.flatMap((provider) => [`${provider.id}-input`, `${provider.id}-output`, `${provider.id}-cache`]);
  const logos = Object.fromEntries(providers.map((provider) => [provider.name, provider.logo ?? ""]));

  return <div className="benchmarks-card">
    <div className="benchmarks-tabs"><span className="bench-tab active">Token Use</span></div>
    <div className="benchmarks-header"><h3 className="bench-title">Token Use <span className="bench-arrow">↗</span></h3><p className="bench-desc">Canonical provider token totals · {comparison.label}</p></div>
    <div className="chart-wrap" style={{ height: 360 }}><BarChart data={rows} config={tokenConfigFor(selection)} stackType="stacked" className="h-full w-full" margins={{ top: 56, right: 12, bottom: 36, left: 50 }}><Grid horizontal /><XAxis dataKey="provider" /><YAxis tickCount={5} tickFormatter={(value) => `${Math.round(value / 1000)}k`} />{keys.map((key) => <Bar key={key} dataKey={key} />)}<BarLabels formatter={(value) => value == null ? "" : `${Math.round(value / 1000)}k`} offset={12} /><BarCategoryLogos categoryKey="provider" logos={logos} /><Legend align="right" /><Tooltip labelKey="provider" valueFormatter={(value) => value == null ? "n/a" : `${Math.round(value).toLocaleString()}`} /></BarChart></div>
    <div className="bench-foot">Lower total is better · {comparison.label}</div>
  </div>;
}
