"use client";

import { useState, useMemo } from "react";

type Filter = "different" | "all" | "bothPassed" | "bothFailed";

const PAGE_SIZE = 15;

const TASK_NAMES = [
  "configure-git","recover-db","fix-nginx","setup-ssl","deploy-app","migrate-data","patch-kernel","optimize-cache","secure-ssh","backup-files",
  "restore-snapshot","analyze-logs","clean-disk","update-packages","test-api","build-image","run-migrations","configure-firewall","monitor-services","tune-postgres",
  "fix-permissions","rotate-keys","install-docker","setup-cron","debug-memory","resolve-dns","benchmark-io","encrypt-volume","scale-workers","audit-security",
  "provision-vm","configure-redis","fix-systemd","parse-json","generate-report","sync-s3","validate-schema","refactor-config","deploy-helm","check-ssl-expiry",
  "purge-cache","profile-cpu","collect-metrics","handle-oauth","test-webhook","update-helm","fix-yaml","manage-users","setup-vpn","compress-logs",
  "verify-checksum","benchmark-network","configure-haproxy","migrate-mongo","fix-imports","schedule-backup","test-load","deploy-canary","investigate-oom","update-cert",
  "seed-database","configure-logging","fix-race-condition","optimize-query","handle-pagination","setup-queue","test-integration","deploy-staging","monitor-latency","fix-cors",
  "rotate-logs","setup-monitoring","validate-input","configure-traefik","test-e2e","cleanup-docker","analyze-traces","fix-dependency","setup-ratelimit","deploy-production",
  "debug-timeout","configure-env","test-unit","optimize-bundle","handle-retries","setup-alerts","migrate-s3","fix-auth","benchmark-api","configure-pgpool",
  "test-regression","deploy-feature","monitor-errors","update-dependencies","fix-utf8","setup-replication",
];

type Task = {
  task: string;
  kourierPassed: boolean;
  electronPassed: boolean;
  kourierDurationSec: number;
  electronDurationSec: number;
  kourierRequests: number;
  electronRequests: number;
  kourierInputTokens: number;
  electronInputTokens: number;
  kourierOutputTokens: number;
  electronOutputTokens: number;
  kourierSpeed: number;
  electronSpeed: number;
  kourierTTFT: number;
  electronTTFT: number;
  kourierSuccess: number;
  electronSuccess: number;
  kourierTimeouts: number;
  electronTimeouts: number;
  failureReason: string | null;
};

const FAILURE_REASONS = ["VerifierTimeoutError","AssertionError","FileNotFound","PermissionDenied","OutputMismatch","DependencyError","Timeout"];

function genTasks(): Task[] {
  const tasks: Task[] = [];
  for (let i = 0; i < 89; i++) {
    const name = TASK_NAMES[i] ?? `task-${String(i+1).padStart(2,"0")}`;
    const h1 = (i * 9301 + 49297) % 233280;
    const h2 = (i * 49297 + 9301) % 233280;
    const r1 = h1 / 233280;
    const r2 = h2 / 233280;
    // Tune to get ~42 different results
    let kourierPassed: boolean;
    let electronPassed: boolean;
    if (i % 11 === 0) { kourierPassed = true; electronPassed = false; }
    else if (i % 13 === 0) { kourierPassed = false; electronPassed = true; }
    else if (i % 7 === 0) { kourierPassed = false; electronPassed = false; }
    else if (i % 5 === 0) { kourierPassed = true; electronPassed = true; }
    else { kourierPassed = r1 > 0.42; electronPassed = r2 > 0.48; }

    const kDuration = 140 + Math.floor(r1 * 200) + (i % 40);
    const eDuration = 150 + Math.floor(r2 * 210) + (i % 37);
    const kReq = 8 + Math.floor(r1 * 16) + (i % 5);
    const eReq = 9 + Math.floor(r2 * 15) + (i % 4);
    const kIn = 45 + Math.floor(r1 * 80);
    const eIn = 48 + Math.floor(r2 * 85);
    const kOut = 8 + Math.floor(r1 * 12);
    const eOut = 9 + Math.floor(r2 * 13);
    const kSpeed = 68 + Math.floor(r1 * 18);
    const eSpeed = 62 + Math.floor(r2 * 17);
    const kTTFT = 0.32 + r1 * 0.35;
    const eTTFT = 0.42 + r2 * 0.4;
    const kSuccess = kourierPassed ? 100 : (r1 > 0.7 ? 94 : 78 + Math.floor(r1*16));
    const eSuccess = electronPassed ? 100 : (r2 > 0.7 ? 92 : 75 + Math.floor(r2*18));
    const kTimeouts = kourierPassed ? (r1 > 0.85 ? 1 : 0) : (r1 > 0.5 ? 1 : 0);
    const eTimeouts = electronPassed ? (r2 > 0.88 ? 1 : 0) : (r2 > 0.5 ? 1 : 0);
    const failureReason = (!kourierPassed || !electronPassed) ? FAILURE_REASONS[i % FAILURE_REASONS.length] : null;

    tasks.push({
      task: name,
      kourierPassed,
      electronPassed,
      kourierDurationSec: kDuration,
      electronDurationSec: eDuration,
      kourierRequests: kReq,
      electronRequests: eReq,
      kourierInputTokens: kIn,
      electronInputTokens: eIn,
      kourierOutputTokens: kOut,
      electronOutputTokens: eOut,
      kourierSpeed: kSpeed,
      electronSpeed: eSpeed,
      kourierTTFT: kTTFT,
      electronTTFT: eTTFT,
      kourierSuccess: kSuccess,
      electronSuccess: eSuccess,
      kourierTimeouts: kTimeouts,
      electronTimeouts: eTimeouts,
      failureReason,
    });
  }
  return tasks;
}

const ALL_TASKS = genTasks();

function fmtDuration(sec: number) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${String(s).padStart(2,"0")}s`;
}

export default function TaskResultsSection() {
  const [filter, setFilter] = useState<Filter>("different");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);

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
        <p className="bench-desc">Terminal-Bench 2.1 — per-task pass/fail · Click a row for full metrics</p>
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
              <th>Requests</th>
            </tr>
          </thead>
          <tbody>
            {pageTasks.map((t) => {
              const isExpanded = expanded === t.task;
              return (
                <>
                  <tr key={t.task} onClick={()=> setExpanded(isExpanded ? null : t.task)} style={{ cursor: "pointer" }} className={isExpanded ? "selected" : ""}>
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
                        <span className="tr-split-k">K {t.kourierRequests}</span>
                        <span className="tr-split-e">E {t.electronRequests}</span>
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
                            <div className="tr-detail-col"><span>Duration</span><span>{fmtDuration(t.kourierDurationSec)}</span><span>{fmtDuration(t.electronDurationSec)}</span></div>
                            <div className="tr-detail-col"><span>Model Requests</span><span>{t.kourierRequests}</span><span>{t.electronRequests}</span></div>
                            <div className="tr-detail-col"><span>Input Tokens</span><span>{t.kourierInputTokens}K</span><span>{t.electronInputTokens}K</span></div>
                            <div className="tr-detail-col"><span>Output Tokens</span><span>{t.kourierOutputTokens}K</span><span>{t.electronOutputTokens}K</span></div>
                            <div className="tr-detail-col"><span>Output Speed</span><span>{t.kourierSpeed} tok/s</span><span>{t.electronSpeed} tok/s</span></div>
                            <div className="tr-detail-col"><span>TTFT</span><span>{t.kourierTTFT.toFixed(2)}s</span><span>{t.electronTTFT.toFixed(2)}s</span></div>
                            <div className="tr-detail-col"><span>Request Success</span><span>{t.kourierSuccess}%</span><span>{t.electronSuccess}%</span></div>
                            <div className="tr-detail-col"><span>Timeouts</span><span>{t.kourierTimeouts}</span><span>{t.electronTimeouts}</span></div>
                          </div>
                          {t.failureReason && (
                            <div className="tr-failure">
                              <span className="tr-failure-label">Failure reason</span>
                              <span className="tr-failure-value">{t.failureReason}</span>
                            </div>
                          )}
                          <div className="tr-detail-actions">
                            <button className="tr-action-btn">View requests</button>
                            <button className="tr-action-btn">View logs</button>
                            <button className="tr-action-btn">View artifacts</button>
                          </div>
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
    </div>
  );
}
