import { loadArtifacts } from "@/lib/artifact-loader";
import SideNav from "./components/SideNav";
import RunSelector from "./components/RunSelector";
import ProviderComparisonSection from "./components/ProviderComparisonSection";
import SpeedSection from "./components/SpeedSection";
import LatencySection from "./components/LatencySection";
import ReliabilitySection from "./components/ReliabilitySection";
import TokenUseSection from "./components/TokenUseSection";
import ContextScalingSection from "./components/ContextScalingSection";
import RunHistorySection from "./components/RunHistorySection";
import BenchmarksSection from "./components/BenchmarksSection";
import TaskResultsSection from "./components/TaskResultsSection";
import { RunSelectionProvider } from "@/lib/run-selection";
export const dynamic = "force-dynamic";

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
  const artifacts = loadArtifacts();
  return (
    <main className="wrap">
      <div className="hero">
        <h1>
          <span>Independent</span>
          <span>benchmark data</span>
        </h1>
        <p className="subtitle">
          Understand the AI landscape to choose the best
          <br />
          model and provider for your use case
        </p>
      </div>

      <RunSelectionProvider artifacts={artifacts}>
        <div className="run-selector-row">
          <RunSelector />
        </div>

        <div className="comparison-layout">
          <SideNav />

          <div className="main-content">
            <section id="provider-comparison" className="content-section">
            <h2 className="comparison-title">
              <span className="sq" aria-hidden />
              Provider Comparison
            </h2>
            <ProviderComparisonSection />
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
      </RunSelectionProvider>
    </main>
  );
}
