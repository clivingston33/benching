"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import {
  createDataset,
  defaultSelection,
  hasSelection,
  selectionLabel,
  type ArtifactDataset,
  type RunSelection,
} from "@/lib/benchmark-data";
import type { CanonicalArtifacts } from "@/lib/artifact-loader";

interface RunSelectionValue {
  selection: RunSelection;
  setSelection: (selection: RunSelection) => void;
  comparisons: ArtifactDataset["comparisonOptions"];
  runs: ArtifactDataset["runOptions"];
  label: string;
  dataset: ArtifactDataset;
  allRuns: ArtifactDataset["allRuns"];
  providers: ArtifactDataset["providers"];
}

const RunSelectionContext = createContext<RunSelectionValue | null>(null);

export function RunSelectionProvider({ children, artifacts }: { children: ReactNode; artifacts: CanonicalArtifacts }) {
  const dataset = useMemo(() => createDataset(artifacts), [artifacts]);
  const [selection, setSelection] = useState<RunSelection>(() => defaultSelection(dataset));
  // Never point at a removed selection merely because ordering changed:
  // retain valid selections, deterministically fall back otherwise.
  const effective = hasSelection(dataset, selection) ? selection : defaultSelection(dataset);
  const label = selectionLabel(dataset, effective);
  const value = useMemo(
    () => ({
      selection: effective,
      setSelection,
      comparisons: dataset.comparisonOptions,
      runs: dataset.runOptions,
      label,
      dataset,
      allRuns: dataset.allRuns,
      providers: dataset.providers,
    }),
    [dataset, effective, label]
  );
  return <RunSelectionContext.Provider value={value}>{children}</RunSelectionContext.Provider>;
}

export function useRunSelection(): RunSelectionValue {
  const value = useContext(RunSelectionContext);
  if (!value) throw new Error("useRunSelection must be used within RunSelectionProvider");
  return value;
}
