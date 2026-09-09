"use client";

import { comparisonRowsFor, getComparison, seriesFor } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

export default function ProviderComparisonSection() {
  const { selection, dataset, label } = useRunSelection();
  const comparison = getComparison(dataset, selection);
  const rows = comparisonRowsFor(dataset, selection);
  const series = seriesFor(comparison.runs);

  return (
    <>
      <div className="table-wrap">
        <table className="comp-table">
          <thead><tr><th className="th-metric" />{series.map((item) => <th key={item.key} className="th-provider" style={{ borderBottomColor: item.color }}><span className="provider-label" style={{ color: item.color }}>{item.name}</span><span className="provider-model">{item.model}{item.disambiguator ? ` · ${item.disambiguator}` : ""}</span></th>)}<th className="th-note" /></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.metric}><td className="td-metric">{row.metric}</td>{series.map((item) => <td key={item.key} className="td-val">{row.values[item.key] ?? "n/a"}</td>)}<td className="td-note">{row.note}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="data-note">{label}. Values are read directly from the canonical comparison artifact.</p>
    </>
  );
}
