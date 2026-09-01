"use client";

import { useChartPart } from "./chart-context";

export interface BarSeriesLogosProps {
  logos: Record<string, string>;
  size?: number;
  yOffset?: number;
}

export function BarSeriesLogos({ logos, size = 18, yOffset = 18 }: BarSeriesLogosProps) {
  const ctx = useChartPart("BarSeriesLogos", "bar");
  if (!ctx.ready) return null;
  const n = ctx.configKeys.length;
  return (
    <g>
      {ctx.data.map((_, i) =>
        ctx.configKeys.map((key) => {
          const src = logos[key];
          if (!src) return null;
          const si = ctx.configKeys.indexOf(key);
          const slot = ctx.barSlot(i, si, n);
          const x = slot.x + slot.width / 2 - size / 2;
          const y = ctx.plot.height + yOffset;
          return <image key={`${i}-${key}`} href={src} x={x} y={y} width={size} height={size} preserveAspectRatio="xMidYMid meet" />;
        })
      )}
    </g>
  );
}
