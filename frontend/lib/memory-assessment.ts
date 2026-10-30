import { BACKEND_URL, backendHeaders } from "./backend";
import type { AnalysisReport } from "./types";

/** Only matching case metadata and the current report are sent; no historical letter text is retrieved. */
export async function explainMemoryMatches(report: AnalysisReport): Promise<AnalysisReport> {
  if (!report.memory_matches?.length) return report;
  try {
    const response = await fetch(`${BACKEND_URL}/assess-memory`, {
      method: "POST", headers: { ...backendHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(report), signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error("Context assessment unavailable");
    const result = await response.json();
    return { ...report, summary: typeof result.summary === "string" && result.summary.trim() ? result.summary : report.summary,
      ai_used: report.ai_used || result.ai_used === true,
      warnings: typeof result.warning === "string" ? [...report.warnings, result.warning] : report.warnings };
  } catch {
    return { ...report, warnings: [...report.warnings, "The AI context check was unavailable. The saved-case matches and risk warning are still included."] };
  }
}
