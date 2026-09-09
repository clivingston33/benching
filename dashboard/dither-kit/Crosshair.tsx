"use client";

import { useChartPart } from "./chart-context";

export interface CrosshairProps {
  /** dash pattern for the line */
  strokeDasharray?: string;
  /** opacity 0-1 */
  opacity?: number;
}

/**
 * Dotted vertical preview line at the hovered x index.
 * Renders in the front SVG layer, only visible while hovering.
 * Works for line/area and bar charts (centered on xCenter).
 */
export function Crosshair({ strokeDasharray = "3 3", opacity = 0.6 }: CrosshairProps) {
  const ctx = useChartPart("Crosshair");
  if (!ctx.ready || ctx.hoverIndex == null || !ctx.isMouseInChart) return null;
  const x = ctx.xCenter(ctx.hoverIndex);
  if (x == null) return null;
  return (
    <line
      x1={x}
      x2={x}
      y1={0}
      y2={ctx.plot.height}
      stroke="currentColor"
      strokeDasharray={strokeDasharray}
      opacity={opacity}
      className="text-muted-foreground pointer-events-none"
    />
  );
}
