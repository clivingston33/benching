"use client";

import { Fragment, useMemo, useState } from "react";
import { getComparison, fmtDuration, fmtTokens, type ComparisonTaskResult, type Provider } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Filter = "different" | "all" | "allPassed" | "allFailed";
const PAGE_SIZE = 15;

export default function TaskResultsSection() {
  const { selection } = useRunSelection();
  const comparison = getComparison(selection);
  const providers = comparison.providers.map((run) => run.provider);
  const [filter, setFilter] = useState<Filter>("different");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const filtered = useMemo(() => comparison.tasks.filter((task) => {
    const results = providers.map((provider) => task.results[provider.id]);
    const passed = results.map((result) => result?.passed ?? false);
    const matchesFilter = filter === "all" || filter === "different" && new Set(passed).size > 1 || filter === "allPassed" && passed.every(Boolean) || filter === "allFailed" && passed.every((value) => !value);
    return matchesFilter && task.taskId.toLowerCase().includes(search.trim().toLowerCase());
  }), [comparison.tasks, filter, providers, search]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageTasks = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const onFilter = (value: Filter) => { setFilter(value); setPage(1); setExpanded(null); };
  const onSearch = (value: string) => { setSearch(value); setPage(1); };
  const columns = providers.length + 3;

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-header" style={{ borderBottom: "none", marginBottom: 0, paddingBottom: 0 }}>
        <h3 className="bench-title">Task Results <span className="bench-arrow">↗</span></h3>
        <p className="bench-desc">{comparison.providers[0]?.benchmark.name ?? "Benchmark"} — {comparison.tasks.length} tasks · {comparison.label} · Click a row for details</p>
      </div>
      <div className="tr-controls">
        <div className="tr-filters">
          <button className={`bench-tab ${filter === "different" ? "active" : ""}`} onClick={() => onFilter("different")}>Different Results</button>
          <button className={`bench-tab ${filter === "all" ? "active" : ""}`} onClick={() => onFilter("all")}>All</button>
          <button className={`bench-tab ${filter === "allPassed" ? "active" : ""}`} onClick={() => onFilter("allPassed")}>All Passed</button>
          <button className={`bench-tab ${filter === "allFailed" ? "active" : ""}`} onClick={() => onFilter("allFailed")}>All Failed</button>
        </div>
        <div className="tr-search-wrap"><span className="tr-search-icon" aria-hidden>⌕</span><input className="tr-search" placeholder="Search tasks..." value={search} onChange={(event) => onSearch(event.target.value)} /></div>
      </div>
      <div className="rh-table-wrap" style={{ marginTop: 12 }}>
        <table className="rh-table">
          <thead><tr><th style={{ width: "32%" }}>Task</th>{providers.map((provider) => <th key={provider.id} style={{ borderBottom: `2px solid ${provider.color}` }}><ProviderLabel provider={provider} /></th>)}<th>Duration</th><th>Verifier</th></tr></thead>
          <tbody>
            {pageTasks.map((task) => {
              const isExpanded = expanded === task.taskId;
              return <Fragment key={task.taskId}>
                <tr onClick={() => setExpanded(isExpanded ? null : task.taskId)} style={{ cursor: "pointer" }} className={isExpanded ? "selected" : ""}>
                  <td className="rh-model" style={{ fontWeight: 600, color: "#e8e8e8" }}>{task.taskId}</td>
                  {providers.map((provider) => <td key={provider.id}><span className={task.results[provider.id]?.passed ? "tr-pass" : "tr-fail"}>{task.results[provider.id]?.passed ? "✓ Pass" : "✕ Fail"}</span></td>)}
                  <td><div className="tr-split-col">{providers.map((provider) => <span key={provider.id} style={{ color: provider.color }}>{provider.name}: {fmtDuration(task.results[provider.id]?.durationSec ?? null)}</span>)}</div></td>
                  <td><div className="tr-split-col">{providers.map((provider) => <span key={provider.id}>{provider.name}: {task.results[provider.id]?.reward?.toFixed(1) ?? "0.0"}</span>)}</div></td>
                </tr>
                {isExpanded && <tr className="tr-detail-row"><td colSpan={columns} style={{ padding: 0, background: "#1f1f1f" }}><TaskDetail task={task} providers={providers} /></td></tr>}
              </Fragment>;
            })}
            {pageTasks.length === 0 && <tr><td colSpan={columns} style={{ textAlign: "center", padding: 24, color: "#9a9a9a" }}>No tasks match filters</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="tr-pagination">
        <div className="tr-showing">Showing {filtered.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length}</div>
        <div className="tr-pages"><button className="tr-page-btn" disabled={currentPage === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>←</button>{Array.from({ length: totalPages }, (_, index) => index + 1).slice(Math.max(0, currentPage - 3), Math.max(0, currentPage - 3) + 6).map((value) => <button key={value} className={`tr-page-btn ${value === currentPage ? "active" : ""}`} onClick={() => setPage(value)}>{value}</button>)}<button className="tr-page-btn" disabled={currentPage === totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>→</button></div>
      </div>
      <div className="bench-foot" style={{ marginTop: 12 }}>{comparison.label}</div>
    </div>
  );
}

function ProviderLabel({ provider }: { provider: Provider }) {
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><img src={provider.logo} alt="" width={16} height={16} style={{ borderRadius: "50%" }} />{provider.name}</span>;
}

function TaskDetail({ task, providers }: { task: ComparisonTaskResult; providers: Provider[] }) {
  return <div className="tr-detail"><div className="tr-detail-title">{task.taskId}</div><div className="tr-detail-grid" style={{ gridTemplateColumns: `repeat(${providers.length + 1}, minmax(0, 1fr))` }}><div className="tr-detail-col tr-detail-col-head"><div></div>{providers.map((provider) => <div key={provider.id}><ProviderLabel provider={provider} /></div>)}</div><DetailRow label="Verifier Reward" providers={providers} value={(result) => result?.reward?.toFixed(1) ?? "0.0"} task={task} /><DetailRow label="Duration" providers={providers} value={(result) => fmtDuration(result?.durationSec ?? null)} task={task} /><DetailRow label="Input Tokens" providers={providers} value={(result) => fmtTokens(result?.inputTokens ?? null)} task={task} /><DetailRow label="Output Tokens" providers={providers} value={(result) => fmtTokens(result?.outputTokens ?? null)} task={task} /></div>{providers.map((provider) => task.results[provider.id]?.exception ? <div className="tr-failure" key={provider.id}><span className="tr-failure-label">{provider.name} failure</span><span className="tr-failure-value">{task.results[provider.id].exception}</span></div> : null)}</div>;
}

function DetailRow({ label, providers, value, task }: { label: string; providers: Provider[]; value: (result: ComparisonTaskResult["results"][string] | undefined) => string; task: ComparisonTaskResult }) {
  return <div className="tr-detail-col"><span>{label}</span>{providers.map((provider) => <span key={provider.id}>{value(task.results[provider.id])}</span>)}</div>;
}
