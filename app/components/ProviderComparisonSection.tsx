"use client";

import { comparisonRowsFor, getComparison } from "@/lib/benchmark-data";
import { presentationFor } from "@/lib/provider-presentation";
import { useRunSelection } from "@/lib/run-selection";

export default function ProviderComparisonSection() {
  const { selection, label } = useRunSelection();
  const comparison = getComparison(selection);
  const rows = comparisonRowsFor(selection);

  return (
    <>
      <div className="table-wrap">
        <table className="comp-table">
          <thead><tr><th className="th-metric" />{comparison.runs.map((run, index) => { const provider = presentationFor(run.provider, index); return <th key={run.run_id} className="th-provider" style={{ borderBottomColor: provider.color }}><span className="provider-label" style={{ color: provider.color }}>{provider.name}</span><span className="provider-model">{run.model}</span></th>; })}<th className="th-note" /></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.metric}><td className="td-metric">{row.metric}</td>{comparison.runs.map((run) => <td key={run.run_id} className="td-val">{row.values[run.provider.id] ?? "n/a"}</td>)}<td className="td-note">{row.note}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="data-note">{label}. Values are read directly from the canonical comparison artifact.</p>
    </>
  );
}
