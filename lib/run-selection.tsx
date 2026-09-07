"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { comparisonOptions, runOptions, type RunSelection } from "@/lib/benchmark-data";

interface RunSelectionValue {
  selection: RunSelection;
  setSelection: (selection: RunSelection) => void;
  comparisons: typeof comparisonOptions;
  runs: typeof runOptions;
  label: string;
}

const RunSelectionContext = createContext<RunSelectionValue | null>(null);

export function RunSelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<RunSelection>(comparisonOptions[0]?.selection ?? "");
  const label = comparisonOptions.find((item) => item.selection === selection)?.label ?? runOptions.find((item) => item.selection === selection)?.label ?? "No artifact selected";
  const value = useMemo(() => ({ selection, setSelection, comparisons: comparisonOptions, runs: runOptions, label }), [selection, label]);
  return <RunSelectionContext.Provider value={value}>{children}</RunSelectionContext.Provider>;
}

export function useRunSelection(): RunSelectionValue {
  const value = useContext(RunSelectionContext);
  if (!value) throw new Error("useRunSelection must be used within RunSelectionProvider");
  return value;
}
