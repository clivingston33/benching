"use client";

import { useState, useMemo } from "react";
import { ALL_TASKS, fmtDuration, APPLES_TO_APPLES, PROVIDERS, PROVIDER_LABEL, logoFor } from "@/lib/benchmark-data";
import type { TaskRow } from "@/lib/benchmark-data";

type Filter = "different" | "all" | "bothPassed" | "bothFailed";

const PAGE_SIZE = 15;

const fmtK = (v: number | null) => (v == null ? "n/a" : `${Math.round(v / 1000)}K`);
const fmtNum = (v: number | null) => (v == null ? "n/a" : String(Math.round(v)));

const ProviderLogo = ({ prov, size = 16 }: { prov: string; size?: number }) => {
  const src = logoFor(prov);
  if (!src) return <span className="tr-provider-dot" style={{ width: size, height: size }} />;
  return <img src={src} alt="" width={size} height={size} style={{ borderRadius: "50%" }} />;
};

export default function TaskResultsSection() {
  const [filter, setFilter] = useState<Filter>("different");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let t = ALL_TASKS;
    if (filter === "different") t = t.filter(x => PROVIDERS.some(p => x.results[p]?.passed) && PROVIDERS.some(p => !x.results[p]?.passed));
    else if (filter === "bothPassed") t = t.filter(x => PROVIDERS.every(p => x.results[p]?.passed));
    else if (filter === "bothFailed") t = t.filter(x => PROVIDERS.every(p => x.results[p]?.passed === false));
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      t = t.filter(x => x.task.toLowerCase().includes(q));
    }
    return t;
  }, [filter, search]);

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
        <p className="bench-desc">
          Terminal-Bench 2.1 — {ALL_TASKS.length} tasks with results from {PROVIDERS.length} providers · Click a row for details
        </p>
      </div>

      <div className="tr-controls">
        <div className="tr-filters">
          <button className={`bench-tab ${filter==="different"?"active":""}`} onClick={()=>onFilter("different")}>Different Results</button>
          <button className={`bench-tab ${filter==="all"?"active":""}`} onClick={()=>onFilter("all")}>All</button>
          <button className={`bench-tab ${filter==="bothPassed"?"active":""}`} onClick={()=>onFilter("bothPassed")}>All Passed</button>
          <button className={`bench-tab ${filter==="bothFailed"?"active":""}`} onClick={()=>onFilter("bothFailed")}>All Failed</button>
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
              {PROVIDERS.map((prov) => (
                <th key={prov} style={{ background: "rgba(255,255,255,0.03)", borderBottom: "2px solid #555" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <ProviderLogo prov={prov} /> {PROVIDER_LABEL[prov]}
                  </span>
                </th>
              ))}
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
                    {PROVIDERS.map((prov) => {
                      const r = t.results[prov];
                      const passed = r?.passed;
                      return (
                        <td key={prov} style={{ background: "rgba(255,255,255,0.02)" }}>
                          <span className={passed ? "tr-pass" : "tr-fail"}>
                            {passed == null ? "—" : passed ? "✓ Pass" : "✕ Fail"}
                          </span>
                        </td>
                      );
                    })}
                    <td>
                      <div className="tr-split-col">
                        {PROVIDERS.map((prov) => (
                          <span key={prov} className="tr-split-k" style={{ display: "block" }}>
                            {PROVIDER_LABEL[prov][0]} {fmtDuration(t.results[prov]?.durationSec ?? null)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <div className="tr-split-col">
                        {PROVIDERS.map((prov) => (
                          <span key={prov} className="tr-split-k" style={{ display: "block" }}>
                            {t.results[prov]?.passed ? "1.0" : "0.0"}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="tr-detail-row">
                      <td colSpan={2 + PROVIDERS.length + 2} style={{ padding: 0, background: "#1f1f1f" }}>
                        <div className="tr-detail">
                          <div className="tr-detail-title">{t.task}</div>
                          <div className="tr-detail-grid">
                            <div className="tr-detail-col tr-detail-col-head">
                              <div></div>
                              {PROVIDERS.map((prov) => (
                                <div key={prov}><span style={{ display:"inline-flex", alignItems:"center", gap:6 }}><ProviderLogo prov={prov} size={14} />{PROVIDER_LABEL[prov]}</span></div>
                              ))}
                            </div>
                            <div className="tr-detail-col"><span>Verifier Reward</span>{PROVIDERS.map((prov) => <span key={prov}>{t.results[prov]?.passed ? "1.0" : "0.0"}</span>)}</div>
                            <div className="tr-detail-col"><span>Duration</span>{PROVIDERS.map((prov) => <span key={prov}>{fmtDuration(t.results[prov]?.durationSec ?? null)}</span>)}</div>
                            <div className="tr-detail-col"><span>Input Tokens</span>{PROVIDERS.map((prov) => <span key={prov}>{fmtK(t.results[prov]?.inputTokens ?? null)}</span>)}</div>
                            <div className="tr-detail-col"><span>Output Tokens</span>{PROVIDERS.map((prov) => <span key={prov}>{fmtK(t.results[prov]?.outputTokens ?? null)}</span>)}</div>
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
              <tr><td colSpan={2 + PROVIDERS.length + 2} style={{ textAlign:"center", padding:24, color:"#9a9a9a" }}>No tasks match filters</td></tr>
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

      <div className="bench-foot" style={{ marginTop: 12 }}>{APPLES_TO_APPLES}</div>
    </div>
  );
}
