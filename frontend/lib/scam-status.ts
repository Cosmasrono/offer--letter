import type { ScamStatus } from "./types";

export const SCAM_STATUS_LABELS: Record<ScamStatus, string> = {
  UNREVIEWED: "Not reviewed", SUSPECTED_SCAM: "Suspected scam", REPORTED_SCAM: "Reported scam · awaiting review",
  CONFIRMED_SCAM: "Confirmed scam", CLEARED: "Scam report dismissed",
};

export function reportStatus(report: { scamStatus?: string | null; userReportedAt?: unknown; riskLevel?: string }): ScamStatus {
  if (report.scamStatus && Object.hasOwn(SCAM_STATUS_LABELS, report.scamStatus)) return report.scamStatus as ScamStatus;
  return report.userReportedAt ? "REPORTED_SCAM" : report.riskLevel === "HIGH" ? "SUSPECTED_SCAM" : "UNREVIEWED";
}
