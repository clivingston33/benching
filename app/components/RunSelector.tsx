"use client";

import { useRunSelection, fmtDate } from "@/lib/run-selection";
import { runDates } from "@/lib/benchmark-data";

export default function RunSelector() {
  const { selection, setSelection, dates } = useRunSelection();
  return (
    <div className="run-selector">
      <div className="run-selector-label">Showing</div>
      <div className="run-selector-control" role="group" aria-label="Select run">
        <button
          className={`run-selector-btn ${selection === "all" ? "active" : ""}`}
          onClick={() => setSelection("all")}
        >
          All runs (average)
        </button>
        {dates.map((d) => (
          <button
            key={d}
            className={`run-selector-btn ${selection === d ? "active" : ""}`}
            onClick={() => setSelection(d)}
          >
            {fmtDate(d)}
          </button>
        ))}
      </div>
    </div>
  );
}
