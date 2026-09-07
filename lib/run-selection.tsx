"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { comparisons, fmtRunLabel, runDates, type RunSelection } from "@/lib/benchmark-data";

interface RunSelectionValue {
  selection: RunSelection;
  setSelection: (selection: RunSelection) => void;
  dates: string[];
  label: string;
}

const RunSelectionContext = createContext<RunSelectionValue | null>(null);

export function RunSelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<RunSelection>("all");
  const dates = useMemo(() => runDates, []);
  const label = comparisons.find((item) => item.id === selection)?.label ?? `${fmtRunLabel(selection)} run`;
  const value = useMemo(() => ({ selection, setSelection, dates, label }), [selection, dates, label]);
  return <RunSelectionContext.Provider value={value}>{children}</RunSelectionContext.Provider>;
}

export function useRunSelection(): RunSelectionValue {
  const value = useContext(RunSelectionContext);
  if (!value) throw new Error("useRunSelection must be used within RunSelectionProvider");
  return value;
}

export const fmtDate = fmtRunLabel;
