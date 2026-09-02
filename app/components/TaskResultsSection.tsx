"use client";

import { useState, useMemo } from "react";
import { taskRowsFor, taskResultsFor, fmtDuration } from "@/lib/benchmark-data";
import type { TaskRow } from "@/lib/benchmark-data";
import { useRunSelection } from "@/lib/run-selection";

type Filter = "different" | "all" | "bothPassed" | "bothFailed";

const PAGE_SIZE = 15;

const fmtK = (v: number | null) => (v == null ? "n/a" : `${Math.round(v / 1000)}K`);

export default function TaskResultsSection() {
  const { selection, label } = useRunSelection();
  const [filter, setFilter] = useState<Filter>("different");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);

  const ALL_TASKS = useMemo<TaskRow[]>(() => taskRowsFor(taskResultsFor(selection)), [selection]);

  const filtered = useMemo(() => {
    let t = ALL_TASKS;
    if (filter === "different") t = t.filter(x => x.kourierPassed !== x.electronPassed);
    else if (filter === "bothPassed") t = t.filter(x => x.kourierPassed && x.electronPassed);
    else if (filter === "bothFailed") t = t.filter(x => !x.kourierPassed && !x.electronPassed);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      t = t.filter(x => x.task.toLowerCase().includes(q));
    }
    return t;
  }, [filter, search, ALL_TASKS]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const curPage = Math.min(page, totalPages);
  const start = (curPage - 1) * PAGE_SIZE;
  const pageTasks = filtered.slice(start, start + PAGE_SIZE);

  const showingFrom = filtered.length === 0 ? 0 : start + 1;
  const showingTo = Math.min(start + PAGE_SIZE, filtered.length);

  const onFilter = (f: Filter) => { setFilter(f); setPage(1); setExpanded(null); };
  const onSearch = (v: string) => { setSearch(v); setPage(1); };

  return (
    <div className="benchmarks-card">
      <div className="benchmarks-header" style={{ borderBottom: "none", marginBottom: 0, paddingBottom: 0 }}>
        <h3 className="bench-title">Task Results <span className="bench-arrow">↗</span></h3>
        <p className="bench-desc">Terminal-Bench 2.1 — {ALL_TASKS.length} tasks with results from both providers · {label} · Click a row for details</p>
      </div>

      <div className="tr-controls">
        <div className="tr-filters">
          <button className={`bench-tab ${filter==="different"?"active":""}`} onClick={()=>onFilter("different")}>Different Results</button>
          <button className={`bench-tab ${filter==="all"?"active":""}`} onClick={()=>onFilter("all")}>All</button>
          <button className={`bench-tab ${filter==="bothPassed"?"active":""}`} onClick={()=>onFilter("bothPassed")}>Both Passed</button>
          <button className={`bench-tab ${filter==="bothFailed"?"active":""}`} onClick={()=>onFilter("bothFailed")}>Both Failed</button>
        </div>
        <div className="tr-search-wrap">
          <span className="tr-search-icon" aria-hidden>⌕</span>
          <input className="tr-search" placeholder="Search tasks..." value={search} onChange={e=>onSearch(e.target.value)} />
        </div>
      </div>

      <div className="rh-table-wrap" style={{ marginTop: 12 }}>
        <table className="rh-table">
          <thead>
            <tr>
              <th style={{ width: "32%" }}>Task</th>
              <th style={{ background: "#1a2e1f", borderBottom: "2px solid #1F704C" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <img src="/kourier.svg" alt="" width={16} height={16} style={{ borderRadius: "50%" }} /> Kourier
                </span>
              </th>
              <th style={{ background: "#241a3a", borderBottom: "2px solid #A242FB" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <img src="/electron.svg" alt="" width={16} height={16} style={{ borderRadius: "50%" }} /> ElectronHub
                </span>
              </th>
              <th>Duration</th>
              <th>Verifier</th>
            </tr>
          </thead>
          <tbody>
            {pageTasks.map((t) => {
              const isExpanded = expanded === t.task;
              return (
                <>
                  <tr onClick={()=> setExpanded(isExpanded ? null : t.task)} style={{ cursor: "pointer" }} className={isExpanded ? "selected" : ""}>
                    <td className="rh-model" style={{ fontWeight: 600, color: "#e8e8e8" }}>{t.task}</td>
                    <td style={{ background: "rgba(31,112,76,0.06)" }}>
                      <span className={t.kourierPassed ? "tr-pass" : "tr-fail"}>
                        {t.kourierPassed ? "✓ Pass" : "✕ Fail"}
                      </span>
                    </td>
                    <td style={{ background: "rgba(162,66,251,0.06)" }}>
                      <span className={t.electronPassed ? "tr-pass" : "tr-fail"}>
                        {t.electronPassed ? "✓ Pass" : "✕ Fail"}
                      </span>
                    </td>
                    <td>
                      <div className="tr-split-col">
                        <span className="tr-split-k">K {fmtDuration(t.kourierDurationSec)}</span>
                        <span className="tr-split-e">E {fmtDuration(t.electronDurationSec)}</span>
                      </div>
                    </td>
                    <td>
                      <div className="tr-split-col">
                        <span className="tr-split-k">{t.kourierPassed ? "1.0" : "0.0"}</span>
                        <span className="tr-split-e">{t.electronPassed ? "1.0" : "0.0"}</span>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="tr-detail-row">
                      <td colSpan={5} style={{ padding: 0, background: "#1f1f1f" }}>
                        <div className="tr-detail">
                          <div className="tr-detail-title">{t.task}</div>
                          <div className="tr-detail-grid">
                            <div className="tr-detail-col tr-detail-col-head">
                              <div></div>
                              <div><span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><img src="/kourier.svg" alt="" width={14} height={14} style={{borderRadius:"50%"}}/>Kourier</span></div>
                              <div><span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><img src="/electron.svg" alt="" width={14} height={14} style={{borderRadius:"50%"}}/>ElectronHub</span></div>
                            </div>
                            <div className="tr-detail-col"><span>Verifier Reward</span><span>{t.kourierPassed ? "1.0" : "0.0"}</span><span>{t.electronPassed ? "1.0" : "0.0"}</span></div>
                            <div className="tr-detail-col"><span>Duration</span><span>{fmtDuration(t.kourierDurationSec)}</span><span>{fmtDuration(t.electronDurationSec)}</span></div>
                            <div className="tr-detail-col"><span>Input Tokens</span><span>{fmtK(t.kourierInputTokens)}</span><span>{fmtK(t.electronInputTokens)}</span></div>
                            <div className="tr-detail-col"><span>Output Tokens</span><span>{fmtK(t.kourierOutputTokens)}</span><span>{fmtK(t.electronOutputTokens)}</span></div>
                          </div>
                          {t.failureReason && (
                            <div className="tr-failure">
                              <span className="tr-failure-label">Failure reason</span>
                              <span className="tr-failure-value">{t.failureReason}</span>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
            {pageTasks.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign:"center", padding:24, color:"#9a9a9a" }}>No tasks match filters</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="tr-pagination">
        <div className="tr-showing">Showing {showingFrom}–{showingTo} of {filtered.length}</div>
        <div className="tr-pages">
          <button className="tr-page-btn" disabled={curPage===1} onClick={()=>setPage(p=>Math.max(1,p-1))}>←</button>
          {Array.from({length: totalPages}, (_, i)=> i+1).slice(Math.max(0, curPage-3), Math.max(0, curPage-3)+6).map(n=> (
            <button key={n} className={`tr-page-btn ${n===curPage?"active":""}`} onClick={()=>setPage(n)}>{n}</button>
          ))}
          <button className="tr-page-btn" disabled={curPage===totalPages} onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>→</button>
        </div>
      </div>

      <div className="bench-foot" style={{ marginTop: 12 }}>{label}</div>
    </div>
  );
}
