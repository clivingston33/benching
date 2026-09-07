"use client";

import { comparisonRowsFor, getComparison } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

export default function ProviderComparisonSection() {
  const { selection } = useRunSelection();
  const comparison = getComparison(selection);
  const rows = comparisonRowsFor(selection);

  return (
    <>
      <div className="table-wrap">
        <table className="comp-table">
          <thead>
            <tr>
              <th className="th-metric" />
              {comparison.providers.map((run) => (
                <th key={run.provider.id} className="th-provider" style={{ borderBottomColor: run.provider.color }}>
                  <span className="provider-label" style={{ color: run.provider.color }}>{run.provider.name}</span>
                  <span className="provider-model">{run.model}</span>
                </th>
              ))}
              <th className="th-note" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.metric}>
                <td className="td-metric">{row.metric}</td>
                {comparison.providers.map((run) => (
                  <td key={run.provider.id} className="td-val">{row.values[run.provider.id] ?? "n/a"}</td>
                ))}
                <td className="td-note">{row.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="data-note">{comparison.label}. Values are supplied by the comparison dataset.</p>
    </>
  );
}
