"use client";

import { Fragment, useMemo, useState } from "react";
import { fmtDuration, fmtTokens, getComparison, seriesFor, taskResultsFor, type CanonicalTaskResult, type RunSeries } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Filter = "different" | "all" | "allPassed" | "allFailed";
type DisplayProvider = RunSeries;
const PAGE_SIZE = 15;

function resultStatus(result: CanonicalTaskResult | undefined) {
  if (!result || result.passed === null) return "— n/a";
  return result.passed ? "✓ Pass" : "✕ Fail";
}

function reward(result: CanonicalTaskResult | undefined) {
  return result?.reward == null ? "n/a" : result.reward.toFixed(1);
}

export default function TaskResultsSection() {
  const { selection, dataset } = useRunSelection();
  const comparison = getComparison(dataset, selection);
  const providers = seriesFor(comparison.runs);
  const tasks = taskResultsFor(dataset, selection);
  const [filter, setFilter] = useState<Filter>("different");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const filtered = useMemo(() => tasks.filter((task) => {
    const passed = providers.map((provider) => task.results[provider.key]?.passed ?? null);
    const matchesFilter = filter === "all" || filter === "different" && new Set(passed).size > 1 || filter === "allPassed" && passed.every((value) => value === true) || filter === "allFailed" && passed.every((value) => value === false);
    return matchesFilter && task.taskId.toLowerCase().includes(search.trim().toLowerCase());
  }), [tasks, filter, providers, search]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageTasks = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const columns = providers.length + 3;
  const onFilter = (value: Filter) => { setFilter(value); setPage(1); setExpanded(null); };
  const onSearch = (value: string) => { setSearch(value); setPage(1); };

  return <div className="benchmarks-card">
    <div className="benchmarks-header" style={{ borderBottom: "none", marginBottom: 0, paddingBottom: 0 }}><h3 className="bench-title">Task Results <span className="bench-arrow">↗</span></h3><p className="bench-desc">{comparison.runs[0]?.benchmark.name ?? "Benchmark"} — {tasks.length} aggregated task/trial records · {comparison.label} · Click a row for details</p></div>
    <div className="tr-controls"><div className="tr-filters"><button className={`bench-tab ${filter === "different" ? "active" : ""}`} onClick={() => onFilter("different")}>Different Results</button><button className={`bench-tab ${filter === "all" ? "active" : ""}`} onClick={() => onFilter("all")}>All</button><button className={`bench-tab ${filter === "allPassed" ? "active" : ""}`} onClick={() => onFilter("allPassed")}>All Passed</button><button className={`bench-tab ${filter === "allFailed" ? "active" : ""}`} onClick={() => onFilter("allFailed")}>All Failed</button></div><div className="tr-search-wrap"><span className="tr-search-icon" aria-hidden>⌕</span><input className="tr-search" placeholder="Search tasks..." value={search} onChange={(event) => onSearch(event.target.value)} /></div></div>
    <div className="rh-table-wrap" style={{ marginTop: 12 }}><table className="rh-table"><thead><tr><th style={{ width: "32%" }}>Task</th>{providers.map((provider) => <th key={provider.key} style={{ borderBottom: `2px solid ${provider.color}` }}><ProviderLabel provider={provider} /></th>)}<th>Duration</th><th>Verifier</th></tr></thead><tbody>{pageTasks.map((task) => { const key = `${task.taskId}:${task.trialId ?? "unknown"}`; const isExpanded = expanded === key; return <Fragment key={key}><tr onClick={() => setExpanded(isExpanded ? null : key)} style={{ cursor: "pointer" }} className={isExpanded ? "selected" : ""}><td className="rh-model" style={{ fontWeight: 600, color: "#e8e8e8" }}>{task.taskId} <span style={{ color: "#888", fontWeight: 400 }}>· trial {task.trialId ?? "n/a"}</span></td>{providers.map((provider) => <td key={provider.key}><span className={task.results[provider.key]?.passed === true ? "tr-pass" : task.results[provider.key]?.passed === false ? "tr-fail" : "tr-neutral"}>{resultStatus(task.results[provider.key])}</span></td>)}<td><div className="tr-split-col">{providers.map((provider) => <span key={provider.key} style={{ color: provider.color }}>{provider.label}: {fmtDuration(task.results[provider.key])}</span>)}</div></td><td><div className="tr-split-col">{providers.map((provider) => <span key={provider.key}>{provider.label}: {reward(task.results[provider.key])}</span>)}</div></td></tr>{isExpanded && <tr className="tr-detail-row"><td colSpan={columns} style={{ padding: 0, background: "#1f1f1f" }}><TaskDetail task={task} providers={providers} /></td></tr>}</Fragment>; })}{pageTasks.length === 0 && <tr><td colSpan={columns} style={{ textAlign: "center", padding: 24, color: "#9a9a9a" }}>No tasks match filters</td></tr>}</tbody></table></div>
    <div className="tr-pagination"><div className="tr-showing">Showing {filtered.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length}</div><div className="tr-pages"><button className="tr-page-btn" disabled={currentPage === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>←</button>{Array.from({ length: totalPages }, (_, index) => index + 1).slice(Math.max(0, currentPage - 3), Math.max(0, currentPage - 3) + 6).map((value) => <button key={value} className={`tr-page-btn ${value === currentPage ? "active" : ""}`} onClick={() => setPage(value)}>{value}</button>)}<button className="tr-page-btn" disabled={currentPage === totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>→</button></div></div>
    <div className="bench-foot" style={{ marginTop: 12 }}>{comparison.label}</div>
  </div>;
}

function ProviderLabel({ provider }: { provider: DisplayProvider }) { return <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{provider.logo && <img src={provider.logo} alt="" width={16} height={16} style={{ borderRadius: "50%" }} />}{provider.label}</span>; }

function TaskDetail({ task, providers }: { task: { taskId: string; trialId: string | null; results: Record<string, CanonicalTaskResult | undefined> }; providers: DisplayProvider[] }) {
  return <div className="tr-detail"><div className="tr-detail-title">{task.taskId} · trial {task.trialId ?? "n/a"}</div><div className="tr-detail-grid" style={{ gridTemplateColumns: `repeat(${providers.length + 1}, minmax(0, 1fr))` }}><div className="tr-detail-col tr-detail-col-head"><div></div>{providers.map((provider) => <div key={provider.key}><ProviderLabel provider={provider} /></div>)}</div><DetailRow label="Verifier Reward" providers={providers} task={task} value={reward} /><DetailRow label="Passed" providers={providers} task={task} value={(result) => result?.passed == null ? "n/a" : String(result.passed)} /><DetailRow label="Duration" providers={providers} task={task} value={fmtDuration} /><DetailRow label="Requests" providers={providers} task={task} value={(result) => result ? String(result.requests) : "n/a"} /><DetailRow label="Input Tokens" providers={providers} task={task} value={(result) => fmtTokens(result?.tokens.input)} /><DetailRow label="Output Tokens" providers={providers} task={task} value={(result) => fmtTokens(result?.tokens.output)} /><DetailRow label="Cache Read" providers={providers} task={task} value={(result) => fmtTokens(result?.tokens.cache_read)} /><DetailRow label="TTFT p50" providers={providers} task={task} value={(result) => result?.latency.ttft_ms_p50 == null ? "n/a" : `${result.latency.ttft_ms_p50.toFixed(1)} ms`} /><DetailRow label="E2E Mean" providers={providers} task={task} value={(result) => result?.latency.end_to_end_latency_ms_mean == null ? "n/a" : `${result.latency.end_to_end_latency_ms_mean.toFixed(1)} ms`} /><DetailRow label="Exception" providers={providers} task={task} value={(result) => result?.exception ?? "n/a"} /></div></div>;
}

function DetailRow({ label, providers, value, task }: { label: string; providers: DisplayProvider[]; value: (result: CanonicalTaskResult | undefined) => string; task: { results: Record<string, CanonicalTaskResult | undefined> } }) { return <div className="tr-detail-col"><span>{label}</span>{providers.map((provider) => <span key={provider.key}>{value(task.results[provider.key])}</span>)}</div>; }
