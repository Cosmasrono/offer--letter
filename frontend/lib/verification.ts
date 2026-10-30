import type { AnalysisReport, VerificationSummary } from "./types";

/** Matches backend/app/verification.py. Coverage never measures the probability an offer is genuine. */
export function verificationSummary(report: AnalysisReport): VerificationSummary {
  if (report.kind === "visa" && report.visa) {
    const items: VerificationSummary["items"] = [{ id: "government", label: "Government visa status", status: "UNVERIFIED", detail: "No government lookup was performed. Use the official portal guidance." },
      ...report.visa.comparisons.map(comparison => ({ id: `visa_${comparison.field}`, label: comparison.field,
        status: comparison.status === "MATCHED" ? "SUPPORTED" as const : comparison.status === "MISMATCH" ? "CONFLICT" as const : "UNVERIFIED" as const, detail: comparison.detail }))];
    const resolved = items.filter(item => ["SUPPORTED", "CONFLICT"].includes(item.status)).length;
    return { level: resolved ? "PARTIAL" : "LIMITED", resolved, required: items.length, items };
  }
  const items: VerificationSummary["items"] = [];
  const categories = [["employer", "Employer registration"], ["discovery", "Independent website research"],
    ["website", "Website details"], ["agency", "Recruitment agency permission"],
    ...(report.source_checks?.some(check => check.check === "sponsorship") ? [["sponsorship", "UK sponsorship record"]] : []),
    ...(report.source_checks?.some(check => check.check === "sponsor_registry") ? [["sponsor_registry", "Current UK sponsor permission"]] : []),
    ...(report.source_checks?.some(check => check.check === "care_provider") ? [["care_provider", "England care-provider registration"]] : [])];
  for (const [category, label] of categories) {
    const sources = (report.source_checks ?? []).filter(check => check.check === category);
    let status: VerificationSummary["items"][number]["status"] = "UNVERIFIED";
    let detail = "No conclusive evidence was saved for this check.";
    if (sources.length) {
      if (sources.some(source => source.status === "MISMATCH")) {
        status = "CONFLICT"; detail = "The checked sources contain differences that need resolving.";
      } else if (sources.some(source => source.status === "MATCHED")) {
        status = "SUPPORTED"; detail = "Details matched in the named source; this does not authenticate the offer.";
      } else if (sources.every(source => source.status === "NOT_APPLICABLE")) {
        status = "NOT_APPLICABLE"; detail = "No recruitment agency was identified.";
      } else detail = sources[0].detail;
    }
    items.push({ id: category, label, status, detail });
  }
  const confirmation = report.offer_confirmation;
  const confirmed = confirmation?.status === "CONFIRMED" && report.scam_status !== "CONFIRMED_SCAM";
  const emailConflict = report.source_checks?.some(check => check.check === "email" && check.status === "MISMATCH");
  items.push({ id: "sender", label: "Recruiter / sender identity", status: confirmed ? "SUPPORTED" : emailConflict ? "CONFLICT" : "UNVERIFIED",
    detail: confirmed ? "A reviewer recorded employer confirmation of the recruiter and offer." : "Email header consistency alone does not authenticate the sender. Confirm the recruiter through independently sourced employer contacts." });
  const denied = confirmation?.status === "DENIED";
  items.push({ id: "offer", label: "Actual offer and terms", status: confirmed ? "SUPPORTED" : denied ? "CONFLICT" : "UNVERIFIED",
    detail: confirmed ? "Direct employer confirmation was recorded by a reviewer." : denied ? "A reviewer recorded that the employer denied this offer." : "The employer has not confirmed the offer reference, recruiter and job terms." });
  const required = items.filter(item => item.status !== "NOT_APPLICABLE").length;
  const resolved = items.filter(item => ["SUPPORTED", "CONFLICT"].includes(item.status)).length;
  const complete = required > 0 && items.every(item => ["SUPPORTED", "NOT_APPLICABLE"].includes(item.status));
  return { level: complete ? "COMPLETE" : resolved ? "PARTIAL" : "LIMITED", resolved, required, items };
}
