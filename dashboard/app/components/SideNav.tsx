"use client";
import { useEffect, useState } from "react";

const ids = [
  "provider-comparison",
  "benchmarks",
  "speed",
  "latency",
  "reliability",
  "token-use",
  "context-scaling",
  "run-history",
  "task-results",
];

const items: { id: string; label: string }[] = [
  { id: "provider-comparison", label: "Provider Comparison" },
  { id: "benchmarks", label: "Benchmarks" },
  { id: "speed", label: "Speed" },
  { id: "latency", label: "Latency" },
  { id: "reliability", label: "Reliability" },
  { id: "token-use", label: "Token Use" },
  { id: "context-scaling", label: "Context Scaling" },
  { id: "run-history", label: "Run History" },
  { id: "task-results", label: "Task Results" },
];
export default function SideNav() {
  const [active, setActive] = useState("provider-comparison");

  useEffect(() => {
    const onScroll = () => {
      const offset = 120;
      let current = ids[0];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        if (el.getBoundingClientRect().top - offset <= 0) current = id;
        else break;
      }
      setActive(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav className="side-nav" aria-label="Sections">
      <ul>
        {items.map((t) => (
          <li key={t.id} className={active === t.id ? "active" : ""}>
            <a
              href={`#${t.id}`}
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(t.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                history.replaceState(null, "", window.location.pathname + window.location.search);
              }}
            >
              <span className="nav-sq" aria-hidden />
              {t.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
