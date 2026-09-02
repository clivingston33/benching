"use client";

import { useRunSelection } from "@/lib/run-selection";
import {
  comparisonRowsFor,
  avgProvider,
  runDates,
  PROVIDERS,
  MODEL_LABEL as _MODEL_LABEL,
} from "@/lib/benchmark-data";

export default function ProviderComparisonSection() {
  const { selection, dates } = useRunSelection();
  const rows = comparisonRowsFor(selection);
  const k = avgProvider(selection, "kourier");
  const e = avgProvider(selection, "electronhub");
  const scopeNote =
    selection === "all"
      ? `Averaged across ${dates.length} full runs`
      : `${selection} run`;
  return (
    <>
      <div className="table-wrap">
        <table className="comp-table">
          <thead>
            <tr>
              <th className="th-metric" />
              <th className="th-provider th-kourier">
                <span className="provider-label">Kourier</span>
                <span className="provider-model">DeepSeek V4 flash 0731</span>
              </th>
              <th className="th-provider th-electron">
                <span className="provider-label">ElectronHub</span>
                <span className="provider-model">DeepSeek V4 flash 0731</span>
              </th>
              <th className="th-note" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.metric}>
                <td className="td-metric">{r.metric}</td>
                <td className="td-val">{r.kourier}</td>
                <td className="td-val">{r.electron}</td>
                <td className="td-note">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="data-note">
        {scopeNote}. Same model on both providers, 89 Terminal-Bench 2.1 tasks each. Request counts: Kourier{" "}
        {(k?.requests ?? 0).toLocaleString()}, ElectronHub {(e?.requests ?? 0).toLocaleString()}. Task pass rate:{" "}
        {k?.tasks_passed}/{k?.tasks_total} vs {e?.tasks_passed}/{e?.tasks_total}.
      </p>
    </>
  );
}
