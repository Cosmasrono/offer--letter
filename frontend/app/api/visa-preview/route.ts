import { createHash } from "node:crypto";
import { BACKEND_URL, backendHeaders } from "@/lib/backend";
import { CONSENT_VERSION, readConsent } from "@/lib/privacy-policy";
import { isDatabaseConfigured } from "@/lib/prisma";
import { ensureReportRetention } from "@/lib/report-privacy";
import { clientIp, isRateLimited, recordAttempt } from "@/lib/rate-limit";
import { validateVisaUpload } from "@/lib/visa-upload";

export async function POST(request: Request) {
  if (request.headers.get("X-Consent-Version") !== CONSENT_VERSION) return Response.json({ error: "Read and accept the current consent notice first." }, { status: 400 });
  if (!isDatabaseConfigured()) return Response.json({ error: "Document storage is unavailable." }, { status: 503 });
  const form = await request.formData();
  if (!readConsent(form)) return Response.json({ error: "Agree to processing and confirm permission to submit these documents." }, { status: 400 });
  const invalid = validateVisaUpload(form);
  if (invalid) return Response.json({ error: invalid }, { status: 400 });
  let stage = "storage";
  try {
    await ensureReportRetention();
    const key = "visa-preview:" + createHash("sha256").update(await clientIp()).digest("hex");
    if (await isRateLimited(key, 10, 60 * 60 * 1000)) return Response.json({ error: "Too many document previews. Please try again later." }, { status: 429 });
    await recordAttempt(key);
    stage = "reading";
    const upstream = new FormData();
    upstream.append("file", form.get("file") as File);
    upstream.append("country", String(form.get("country")));
    if (form.get("offerFile") instanceof File) upstream.append("offer_file", form.get("offerFile") as File);
    const response = await fetch(`${BACKEND_URL}/visa/preview`, { method: "POST", body: upstream, headers: backendHeaders(), signal: AbortSignal.timeout(240_000) });
    if (!response.ok) return Response.json({ code: "DOCUMENT_NOT_CHECKED", error: "Not checked — the visa or attached offer could not be read in a supported format. Try a clearer copy or remove the optional offer. You have not been charged." }, { status: response.status === 413 ? 413 : 422 });
    return Response.json(await response.json(), { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    console.error("Visa preview unavailable:", stage, error instanceof Error ? error.name : "UnknownError");
    return Response.json({ error: stage === "storage" ? "Document storage is temporarily unavailable. Please try again later." : "The document-reading service is unavailable. Please try again." }, { status: 503 });
  }
}
