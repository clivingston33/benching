import SideNav from "./components/SideNav";
import SpeedSection from "./components/SpeedSection";
import LatencySection from "./components/LatencySection";
import ReliabilitySection from "./components/ReliabilitySection";
import TokenUseSection from "./components/TokenUseSection";
import ContextScalingSection from "./components/ContextScalingSection";
import RunHistorySection from "./components/RunHistorySection";
import BenchmarksSection from "./components/BenchmarksSection";
import TaskResultsSection from "./components/TaskResultsSection";
import { comparisonRows, APPLES_TO_APPLES, providers, PROVIDERS, PROVIDER_LABEL, MODEL_LABEL } from "@/lib/benchmark-data";

function Section({ id, title, children }: { id: string; title: string; children?: React.ReactNode }) {
  return (
    <section id={id} className="content-section">
      <h2 className="comparison-title">
        <span className="sq" aria-hidden />
        {title}
      </h2>
      {children ?? <p className="section-placeholder">Content for {title} — coming soon.</p>}
    </section>
  );
}

export default function Home() {
  return (
    <main className="wrap">
      <div className="hero">
        <h1>
          <span>Independent</span>
          <span>analysis of AI</span>
        </h1>
        <p className="subtitle">
          Understand the AI landscape to choose the best
          <br />
          model and provider for your use case
        </p>
      </div>

      <div className="comparison-layout">
        <SideNav />

        <div className="main-content">
          <section id="provider-comparison" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Provider Comparison
            </h2>
            <div className="table-wrap">
              <table className="comp-table">
                <thead>
                  <tr>
                    <th className="th-metric" />
                    {PROVIDERS.map((prov) => (
                      <th key={prov} className={`th-provider ${prov === "kourier" ? "th-kourier" : prov === "electronhub" ? "th-electron" : ""}`}>
                        <span className="provider-label">{PROVIDER_LABEL[prov]}</span>
                        <span className="provider-model">{MODEL_LABEL}</span>
                      </th>
                    ))}
                    <th className="th-note" />
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((r) => (
                    <tr key={r.metric}>
                      <td className="td-metric">{r.metric}</td>
                      {PROVIDERS.map((prov) => (
                        <td key={prov} className="td-val">{r.values[prov]}</td>
                      ))}
                      <td className="td-note">{r.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="data-note">
              {APPLES_TO_APPLES} {" "}
              {PROVIDERS.map((prov) => (
                <span key={prov}>
                  {PROVIDER_LABEL[prov]}: {providers[prov].requests.toLocaleString()} requests, {providers[prov].tasks_passed}/
                  {providers[prov].tasks_total} tasks passed{" "}
                </span>
              ))}
            </p>
          </section>
          <section id="benchmarks" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Benchmarks
            </h2>
            <BenchmarksSection />
          </section>

          <section id="speed" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Speed
            </h2>
            <SpeedSection />
          </section>

          <section id="latency" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Latency
            </h2>
            <LatencySection />
          </section>

          <section id="reliability" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Reliability
            </h2>
            <ReliabilitySection />
          </section>

          <section id="token-use" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Token Use
            </h2>
            <TokenUseSection />
          </section>

          <section id="context-scaling" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Context Scaling
            </h2>
            <ContextScalingSection />
          </section>

          <section id="run-history" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Run History
            </h2>
            <RunHistorySection />
          </section>

          <section id="task-results" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Task Results
            </h2>
            <TaskResultsSection />
          </section>
        </div>
      </div>
    </main>
  );
}
