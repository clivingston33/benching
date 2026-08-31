"use client";

import { useChartPart } from "./chart-context";

export interface BarCategoryLogosProps {
  categoryKey: string;
  logos: Record<string, string>;
  size?: number;
  yOffset?: number;
}

export function BarCategoryLogos({ categoryKey, logos, size = 18, yOffset = 18 }: BarCategoryLogosProps) {
  const ctx = useChartPart("BarCategoryLogos", "bar");
  if (!ctx.ready) return null;
  return (
    <g>
      {ctx.data.map((row, i) => {
        const cat = String(row[categoryKey] ?? "");
        const src = logos[cat] ?? logos[cat.toLowerCase()] ?? logos[cat.toUpperCase()];
        if (!src) return null;
        const x = (ctx.xCenter(i) ?? 0) - size / 2;
        const y = ctx.plot.height + yOffset;
        return <image key={i} href={src} x={x} y={y} width={size} height={size} preserveAspectRatio="xMidYMid meet" />;
      })}
    </g>
  );
}
