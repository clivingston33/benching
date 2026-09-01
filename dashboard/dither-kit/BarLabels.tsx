"use client";

import { useChartPart } from "./chart-context";

export interface BarLabelsProps {
  /** Per-value formatter — defaults to raw value */
  formatter?: (value: number, dataKey: string, index: number) => string;
  /** px gap between bar top and label baseline */
  offset?: number;
}

/**
 * Value labels rendered above each bar. Works for grouped and stacked bars.
 * For stacked, labels are placed at the top of the stack (highest y1 per index).
 * Rendered in the front SVG layer.
 */
export function BarLabels({ formatter, offset = 6 }: BarLabelsProps) {
  const ctx = useChartPart("BarLabels", "bar");
  if (!ctx.ready) return null;

  const isStacked = ctx.stackType === "stacked" || ctx.stackType === "percent";

  if (isStacked) {
    // One label per x-index at the stack top
    return (
      <g className="font-mono text-[10px] font-semibold">
        {ctx.data.map((_, i) => {
          let maxY = -Infinity;
          let total = 0;
          for (const k of ctx.configKeys) {
            const b = ctx.bands[k]?.[i];
            if (!b) continue;
            total += b[1] - b[0];
            if (b[1] > maxY) maxY = b[1];
          }
          if (!Number.isFinite(maxY)) return null;
          const x = ctx.xCenter(i);
          const y = ctx.y(maxY) - offset;
          const label = formatter ? formatter(total, "total", i) : String(Math.round(total));
          if (!x && x !== 0) return null;
          return (
            <text key={i} x={x} y={y} textAnchor="middle" dominantBaseline="auto" fill="#e8e8e8">
              {label}
            </text>
          );
        })}
      </g>
    );
  }

  // Grouped: one label per series per index, centered over its bar slot
  return (
    <g className="font-mono text-[10px] font-semibold">
      {ctx.configKeys.map((key) =>
        ctx.bands[key]?.map((b, i) => {
          const si = ctx.configKeys.indexOf(key);
          const slot = ctx.barSlot(i, si, ctx.configKeys.length);
          const x = slot.x + slot.width / 2;
          const y = ctx.y(b[1]) - offset;
          const raw = b[1] - b[0];
          const label = formatter ? formatter(raw, key, i) : String(Math.round(raw));
          return (
            <text key={`${key}-${i}`} x={x} y={y} textAnchor="middle" dominantBaseline="auto" fill="#e8e8e8">
              {label}
            </text>
          );
        })
      )}
    </g>
  );
}
