import SideNav from "./components/SideNav";
import SpeedSection from "./components/SpeedSection";
import LatencySection from "./components/LatencySection";
import ReliabilitySection from "./components/ReliabilitySection";
import TokenUseSection from "./components/TokenUseSection";
import ContextScalingSection from "./components/ContextScalingSection";
import RunHistorySection from "./components/RunHistorySection";
import BenchmarksSection from "./components/BenchmarksSection";
import TaskResultsSection from "./components/TaskResultsSection";
import { comparisonRows, APPLES_TO_APPLES, providers, MODELS } from "@/lib/benchmark-data";

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
                    <th className="th-provider th-kourier">
                      <span className="provider-label">Kourier</span>
                      <span className="provider-model">{MODELS.kourier}</span>
                    </th>
                    <th className="th-provider th-electron">
                      <span className="provider-label">ElectronHub</span>
                      <span className="provider-model">{MODELS.electronhub}</span>
                    </th>
                    <th className="th-note" />
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((r) => (
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
              {APPLES_TO_APPLES} Request counts: Kourier {providers.kourier.requests.toLocaleString()}, ElectronHub{" "}
              {providers.electronhub.requests.toLocaleString()} (smoke, 3 tasks each). Kourier's higher count reflects
              retried calls during its adaptive-rejection-sampler timeout.
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
