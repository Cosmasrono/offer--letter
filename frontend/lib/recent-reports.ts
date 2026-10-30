import type { Kind, RiskLevel } from "./types";

// Reports checked in this browser, so a guest can return to earlier results while checking new ones.
// Signed-in users also have their account history; this list is a per-device convenience only.
export type RecentReport = { id: string; name: string; kind: Kind; checkedAt: string; risk?: RiskLevel };

const KEY = "olc-recent-reports";
const LIMIT = 10;
export const RECENT_REPORTS_EVENT = "olc-recent-reports-changed";

export function recentReports(): RecentReport[] {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(saved) ? saved.filter((item) => typeof item?.id === "string" && /^[a-f0-9]{24}$/.test(item.id)) : [];
  } catch {
    return []; // Browser storage is optional.
  }
}

function save(reports: RecentReport[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(reports.slice(0, LIMIT)));
    window.dispatchEvent(new Event(RECENT_REPORTS_EVENT));
  } catch { /* Browser storage is optional. */ }
}

export function rememberReport(report: RecentReport) {
  save([report, ...recentReports().filter((item) => item.id !== report.id)]);
}

/** The scan response has no risk while findings are locked; record it once the report is shown. */
export function setReportRisk(id: string, risk: RiskLevel) {
  const reports = recentReports();
  if (reports.some((item) => item.id === id && item.risk !== risk)) save(reports.map((item) => item.id === id ? { ...item, risk } : item));
}

export function forgetReport(id: string) {
  save(recentReports().filter((item) => item.id !== id));
}
