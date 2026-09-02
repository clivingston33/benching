"use client";

import { createContext, useContext, useState, useCallback, useMemo, ReactNode } from "react";
import { runDates, latestRun, RunSelection } from "@/lib/benchmark-data";

interface RunSelectionValue {
  /** "all" = average across runs; otherwise a run date string. */
  selection: RunSelection;
  setSelection: (s: RunSelection) => void;
  /** available run dates (oldest → newest) plus "all" semantics. */
  dates: string[];
  /** human label for the currently active dataset. */
  label: string;
}

const RunSelectionContext = createContext<RunSelectionValue | null>(null);

const fmt = (date: string) => {
  const d = new Date(date + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};

export function RunSelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<RunSelection>("all");
  const dates = useMemo(() => runDates, []);
  const label =
    selection === "all"
      ? `All runs (${dates.length} · average)`
      : `${fmt(selection)} run`;
  const value = useMemo(
    () => ({ selection, setSelection, dates, label }),
    [selection, dates, label],
  );
  return <RunSelectionContext.Provider value={value}>{children}</RunSelectionContext.Provider>;
}

export function useRunSelection(): RunSelectionValue {
  const ctx = useContext(RunSelectionContext);
  if (!ctx) throw new Error("useRunSelection must be used within RunSelectionProvider");
  return ctx;
}

/** fmt export shared by selector + context */
export { fmt as fmtDate };
