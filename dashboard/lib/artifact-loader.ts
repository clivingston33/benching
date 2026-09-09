import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import summaryArtifact from "@/data/summary.json";
import comparisonJanuary from "@/data/comparison-20260102.json";
import {
  classifyArtifact,
  comparisonIdentityErrors,
  comparisonSchemaErrors,
  projectComparison,
  projectSummary,
  summarySchemaErrors,
  type ArtifactNotice,
} from "@/lib/contract";
import type { CanonicalComparison, CanonicalRunSummary } from "@/lib/canonical-types";

export type { ArtifactNotice };

export interface CanonicalArtifacts {
  summary: CanonicalRunSummary | null;
  summaries: CanonicalRunSummary[];
  comparisons: CanonicalComparison[];
  notices: ArtifactNotice[];
}

function readJson(file: string): unknown {
  return JSON.parse(readFileSync(file, "utf8"));
}

function classifySummaryValue(value: unknown, label: string, notices: ArtifactNotice[]): CanonicalRunSummary | null {
  const { kind, version } = classifyArtifact(value);
  if (kind !== "summary") {
    notices.push({ file: label, kind: "invalid", reason: "not a run summary artifact" });
    return null;
  }
  if (typeof version === "number" && version !== 1) {
    notices.push({ file: label, kind: "unsupported_version", reason: `unsupported schema version ${version}` });
    return null;
  }
  const errors = summarySchemaErrors(value);
  if (errors.length > 0) {
    notices.push({ file: label, kind: "invalid", reason: errors[0] });
    return null;
  }
  return projectSummary(value as CanonicalRunSummary);
}

function loadSummaryFile(file: string, label: string, notices: ArtifactNotice[]): CanonicalRunSummary | null {
  let value: unknown;
  try {
    value = readJson(file);
  } catch (error) {
    notices.push({ file: label, kind: error instanceof SyntaxError ? "invalid" : "unreadable", reason: error instanceof SyntaxError ? "invalid JSON" : "unreadable file" });
    return null;
  }
  return classifySummaryValue(value, label, notices);
}

function classifyComparisonValue(value: unknown, label: string, notices: ArtifactNotice[]): CanonicalComparison | null {
  const { kind, version } = classifyArtifact(value);
  if (kind !== "comparison") {
    notices.push({ file: label, kind: "invalid", reason: "not a comparison artifact" });
    return null;
  }
  if (typeof version === "number" && version !== 1) {
    notices.push({ file: label, kind: "unsupported_version", reason: `unsupported schema version ${version}` });
    return null;
  }
  const errors = comparisonSchemaErrors(value);
  if (errors.length > 0) {
    notices.push({ file: label, kind: "invalid", reason: errors[0] });
    return null;
  }
  const candidate = value as CanonicalComparison;
  for (const [index, run] of candidate.runs.entries()) {
    const runErrors = summarySchemaErrors(run);
    if (runErrors.length > 0) {
      notices.push({ file: label, kind: "invalid", reason: `runs[${index}]: ${runErrors[0]}` });
      return null;
    }
  }
  const identityErrors = comparisonIdentityErrors(candidate);
  if (identityErrors.length > 0) {
    notices.push({ file: label, kind: "invalid", reason: identityErrors[0] });
    return null;
  }
  return projectComparison(candidate);
}

function loadComparisonFile(file: string, label: string, notices: ArtifactNotice[]): CanonicalComparison | null {
  let value: unknown;
  try {
    value = readJson(file);
  } catch (error) {
    notices.push({ file: label, kind: error instanceof SyntaxError ? "invalid" : "unreadable", reason: error instanceof SyntaxError ? "invalid JSON" : "unreadable file" });
    return null;
  }
  return classifyComparisonValue(value, label, notices);
}

/** Load + validate + project every artifact in a directory. Never throws for data problems. */
export function loadArtifactsFromDirectory(directory: string): CanonicalArtifacts {
  const notices: ArtifactNotice[] = [];
  const summaries: CanonicalRunSummary[] = [];
  const comparisons: CanonicalComparison[] = [];
  let entries;
  try {
    const root = path.resolve(directory);
    const stats = statSync(root);
    if (!stats.isDirectory()) throw new Error(`not a directory: ${directory}`);
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    notices.push({ file: directory, kind: "unreadable", reason: "data directory missing or inaccessible" });
    return { summary: null, summaries, comparisons, notices };
  }
  const root = path.resolve(directory);
  for (const entry of entries.filter((item) => item.isDirectory()).sort((a, b) => a.name.localeCompare(b.name))) {
    const file = path.join(root, entry.name, "summary.json");
    let isFile = false;
    try {
      isFile = existsSync(file) && statSync(file).isFile();
    } catch {
      notices.push({ file: `${entry.name}/summary.json`, kind: "unreadable", reason: "unreadable file" });
      continue;
    }
    if (!isFile) continue;
    const summary = loadSummaryFile(file, `${entry.name}/summary.json`, notices);
    if (summary) summaries.push(summary);
  }
  for (const entry of entries.filter((item) => item.isFile() && /^comparison-.*\.json$/.test(item.name)).sort((a, b) => a.name.localeCompare(b.name))) {
    const comparison = loadComparisonFile(path.join(root, entry.name), entry.name, notices);
    if (comparison) comparisons.push(comparison);
  }
  let summary: CanonicalRunSummary | null = null;
  for (const current of summaries) {
    if (!summary || current.created_at_utc > summary.created_at_utc) summary = current;
  }
  return { summary, summaries, comparisons, notices };
}

export function loadArtifacts(): CanonicalArtifacts {
  if (process.env.BENCHING_DATA_DIR) return loadArtifactsFromDirectory(process.env.BENCHING_DATA_DIR);
  const notices: ArtifactNotice[] = [];
  const summary = classifySummaryValue(summaryArtifact, "summary.json", notices);
  if (!summary) throw new Error(`bundled fixture invalid: ${notices[0]?.reason ?? "unknown"}`);
  const comparison = classifyComparisonValue(comparisonJanuary, "comparison-20260102.json", notices);
  if (!comparison) throw new Error(`bundled fixture invalid: ${notices[0]?.reason ?? "unknown"}`);
  return { summary, summaries: [summary], comparisons: [comparison], notices };
}

export const artifacts = loadArtifacts();
