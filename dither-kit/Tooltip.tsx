"use client"

import { useEffect, useRef, useState } from "react"
import { useCommonChart } from "./common-context"
import { cn } from "./lib"
import { rgb } from "./palette"
import { usePresence } from "./use-presence"

export type TooltipVariant = "default" | "frosted-glass"

export interface TooltipProps {
  /** Config key whose value supplies the tooltip heading (e.g. `"month"`). */
  labelKey?: string
  /** Per-value formatter for tooltip rows. */
  valueFormatter?: (value: number, name: string) => string
  /** Visual style of the tooltip card. */
  variant?: TooltipVariant
}

const VARIANT: Record<TooltipVariant, string> = {
  default: "bg-[#2a2a2a] border-[#444]",
  "frosted-glass": "bg-[#2a2a2a]/80 backdrop-blur-sm border-[#444]",
}

/** Leave transition duration — must match the CSS opacity transition. */
const TOOLTIP_LEAVE_MS = 180

/**
 * Floating chart tooltip — follows the hovered index, lists each series'
 * value, and fades out (retaining its last content) when the pointer leaves.
 *
 * React port of `Tooltip.vue`. The Vue `<Transition name="dk-tooltip">` with
 * `v-if="show"` becomes a `usePresence`-gated render that toggles a
 * `dk-tooltip-hide` class for the fade (guide §6). The top/left glide
 * transition lives in `transitions.css` as `.dk-tooltip-card`.
 *
 * Sets `Tooltip.chartLayer = "dom"` so the chart root routes it into the DOM
 * layer (guide §8).
 */
export function Tooltip({
  labelKey,
  valueFormatter,
  variant = "default",
}: TooltipProps) {
  const chart = useCommonChart()
  const show = chart.ready && chart.hoverIndex != null

  // Retain the last hovered index so the card keeps its content while fading
  // out — mirrors the Vue `lastIndex` ref + `watch(hoverIndex)`.
  const lastIndex = useRef(0)
  if (chart.hoverIndex != null) lastIndex.current = chart.hoverIndex
  const [retained, setRetained] = useState(0)
  useEffect(() => {
    if (chart.hoverIndex != null) setRetained(chart.hoverIndex)
  }, [chart.hoverIndex])

  const present = usePresence(show, TOOLTIP_LEAVE_MS)
  const index = chart.hoverIndex ?? retained
  const heading = chart.heading(index, labelKey)
  const items = chart.itemsAt(index)

  if (!present || items.length === 0) return null

  return (
    <div
      className={cn(
        "dk-tooltip-card pointer-events-none absolute z-10 rounded-md border p-3 shadow-lg",
        VARIANT[variant],
        !show && "dk-tooltip-hide"
      )}
      style={{
        top: `${chart.tooltipTop}px`,
        left: `${chart.tooltipLeft}px`,
        transform: "translate(-50%, -115%)",
        minWidth: 168,
        maxWidth: 240,
        backgroundColor: variant === "default" ? "#2a2a2a" : undefined,
        borderColor: "#444",
      }}
    >
      {heading ? (
        <div className="mb-0.5 font-mono text-[10px] text-[#9a9a9a]">
          {heading}
        </div>
      ) : null}
      <div className="flex flex-col gap-0.5">
        {items
          .filter((item) => {
            if (item.value === 0) {
              const formatted = valueFormatter ? valueFormatter(item.value, item.name) : ""
              return formatted !== "" && formatted !== "0" && formatted !== "0%" && formatted !== "0 tok/s"
            }
            return true
          })
          .map((item) => (
          <div
            key={item.name}
            className="flex items-center gap-1.5 font-mono text-[11px] tabular-nums"
            style={{ opacity: item.dimmed ? 0.4 : 1, color: "#e8e8e8" }}
          >
            <span
              className="size-2 rounded-[1px]"
              style={{ backgroundColor: rgb(item.seed.fill) }}
            />
            <span className="text-[#9a9a9a]">{item.label}</span>
            <span className="ml-auto pl-2 text-[#e8e8e8]">
              {valueFormatter
                ? valueFormatter(item.value, item.name)
                : item.value.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Route into the DOM layer (absolutely positioned over the chart). */
Tooltip.chartLayer = "dom" as const
