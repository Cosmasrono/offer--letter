import { BACKEND_URL, backendHeaders } from "@/lib/backend";
import { findCheckCredit, spendCheckCredit } from "@/lib/payments";
import { isDatabaseConfigured } from "@/lib/prisma";
import { applyCommunityReports, saveReport } from "@/lib/reports";
import { explainMemoryMatches } from "@/lib/memory-assessment";
import { getCurrentUser } from "@/lib/session";
import type { AnalysisReport, AnalyzeResponse } from "@/lib/types";
import { cookies } from "next/headers";
import { CONSENT_VERSION, MANAGEMENT_COOKIE, REPORT_RETENTION_DAYS, readConsent, reportExpiry } from "@/lib/privacy-policy";
import { ensureReportRetention, hashManagementToken, managementToken } from "@/lib/report-privacy";
import { validateVisaUpload } from "@/lib/visa-upload";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_PASTED_CHARS = 20_000;

export async function POST(request: Request) {
  if (request.headers.get("X-Consent-Version") !== CONSENT_VERSION) return Response.json({ error: "Please read and accept the current consent notice before submitting a document." }, { status: 400 });
  // A scan must be stored before it can be purchased. Never fall back to sending findings to the browser.
  if (!isDatabaseConfigured()) return Response.json({ error: "Report storage is unavailable. Please try again later." }, { status: 503 });
  const form = await request.formData();
  const consent = readConsent(form);
  if (!consent) return Response.json({ error: "Please agree to document processing and confirm you are authorised to submit it." }, { status: 400 });
  try {
    await ensureReportRetention();
  } catch {
    return Response.json({ error: "Document storage is temporarily unavailable. Please try again later." }, { status: 503 });
  }
  const user = await getCurrentUser();
  const browserToken = await managementToken();
  const consentedAt = new Date();
  const country = form.get("country");
  const kind = form.get("kind") === "visa" ? "visa" : form.get("kind") === "message" ? "message" : "letter";
  if (kind === "visa") {
    const invalid = validateVisaUpload(form);
    if (invalid) return Response.json({ error: invalid }, { status: 400 });
    const review = form.get("visaReview");
    if (typeof review !== "string" || review.length > 20_000) return Response.json({ error: "Review the visa details before checking." }, { status: 400 });
    try { if (JSON.parse(review)?.reviewed !== true) throw new Error(); }
    catch { return Response.json({ error: "Confirm that you reviewed the visa details." }, { status: 400 }); }
  } else if (form.has("offerFile") || form.has("visaReview")) return Response.json({ error: "Document comparison requires a visa check." }, { status: 400 });
  const pasted = form.get("text");
  let file = form.get("file");
  if (!(file instanceof File) && typeof pasted === "string" && pasted.trim()) {
    if (pasted.length > MAX_PASTED_CHARS) return Response.json({ error: "That text is too long. Paste just the job ad or message." }, { status: 413 });
    file = new File([pasted], "pasted-message.txt", { type: "text/plain" });
  }
  if (!(file instanceof File) || file.size === 0) {
    return Response.json({ error: kind === "message" ? "Paste the job ad or message, or attach a screenshot." : "Please choose a PDF or image of the offer letter." }, { status: 400 });
  }
  if (file.size > MAX_BYTES) return Response.json({ error: "File is too large. The limit is 10 MB." }, { status: 413 });
  if (!["pdf", "png", "jpg", "jpeg", "webp", "txt", "eml"].includes(file.name.split(".").pop()?.toLowerCase() ?? "")) {
    return Response.json({ code: "DOCUMENT_NOT_CHECKED", error: "Not checked — file type not recognized. Choose a PDF, image, TXT or original EML email." }, { status: 415 });
  }

  const upstream = new FormData();
  upstream.append("file", file, file.name);
  upstream.append("kind", kind);
  if (kind === "visa") {
    upstream.append("visa_review", form.get("visaReview") as string);
    if (form.get("offerFile") instanceof File) upstream.append("offer_file", form.get("offerFile") as File);
  }
  if (typeof country === "string" && country) upstream.append("country", country);
  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${BACKEND_URL}/analyze`, { method: "POST", body: upstream, headers: backendHeaders() });
  } catch {
    return Response.json({ error: "The scanning service is unavailable. Please try again shortly." }, { status: 502 });
  }
  if (!backendResponse.ok) {
    // Do not relay upstream bodies that might include extracted text or findings.
    if ([400, 415, 422].includes(backendResponse.status)) return Response.json({ code: "DOCUMENT_NOT_CHECKED", error: "Not checked — the document could not be recognized or read. Try a clearer photo, the original PDF or original EML email. You have not been charged." }, { status: 422 });
    return Response.json({ error: "The document could not be scanned. Try a clearer photo or the original PDF." }, { status: backendResponse.status });
  }
  let report = (await backendResponse.json()) as AnalysisReport;
  if (!report.text_excerpt.trim()) return Response.json({ code: "DOCUMENT_NOT_CHECKED", error: "Not checked — no text could be read. Upload a clearer photo or the original PDF. You have not been charged." }, { status: 422 });

  let id: string;
  try {
    const baseline = { score: report.score, riskLevel: report.risk_level };
    if (kind !== "visa") {
      report = await applyCommunityReports(report);
      report = await explainMemoryMatches(report);
    }
    id = await saveReport(report, user?.id ?? null, baseline, {
      consentVersion: consent.version, consentedAt, memoryConsent: consent.memoryConsent,
      managementTokenHash: hashManagementToken(browserToken), expiresAt: reportExpiry(consentedAt),
    });
    if (!id) throw new Error("No saved report ID");
  } catch {
    console.error("Could not save scanned report.");
    return Response.json({ error: "Your scan could not be saved. Please try again. You have not been charged." }, { status: 503 });
  }

  (await cookies()).set(MANAGEMENT_COOKIE, browserToken, {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/",
    maxAge: REPORT_RETENTION_DAYS * 24 * 60 * 60,
  });

  // Honour an unused payment from the previous pay-before-scanning flow, without charging twice.
  const paymentId = form.get("paymentId");
  const paymentToken = form.get("paymentToken");
  if (typeof paymentId === "string" && typeof paymentToken === "string") {
    const credit = await findCheckCredit(paymentId, paymentToken, user);
    if (credit && await spendCheckCredit(credit.id, id)) {
      return Response.json({ id, report: null, token: credit.token } satisfies AnalyzeResponse, { headers: { "Cache-Control": "private, no-store" } });
    }
  }
  return Response.json({ id, report: null } satisfies AnalyzeResponse, { headers: { "Cache-Control": "private, no-store" } });
}
