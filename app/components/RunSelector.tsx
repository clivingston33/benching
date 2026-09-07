"use client";

import { useRunSelection } from "@/lib/run-selection";

export default function RunSelector() {
  const { selection, setSelection, comparisons, runs } = useRunSelection();
  return (
    <div className="run-selector">
      <div className="run-selector-label">Showing</div>
      <div className="run-selector-control" role="group" aria-label="Select artifact">
        {comparisons.map((item) => <button key={item.selection} className={`run-selector-btn ${selection === item.selection ? "active" : ""}`} onClick={() => setSelection(item.selection)}>{item.label}</button>)}
        {runs.map((item) => <button key={item.selection} className={`run-selector-btn ${selection === item.selection ? "active" : ""}`} onClick={() => setSelection(item.selection)}>{item.label}</button>)}
      </div>
    </div>
  );
}
