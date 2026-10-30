import type { OfferConfirmation } from "./types";

/** Only server-authored, audited review-history entries can establish employer confirmation. */
export function readOfferConfirmation(history: unknown, scamStatus?: string | null): OfferConfirmation | null {
  if (!Array.isArray(history)) return null;
  const entry = [...history].reverse().find(value => value?.action === "RECORD_OFFER_CONFIRMATION");
  if (history.slice(history.indexOf(entry) + 1).some(value => value?.action === "CONFIRM_SCAM")) return null;
  const value = entry?.confirmation;
  if (!value || !/^[a-f0-9]{24}$/i.test(entry.reviewerId ?? "") || !["CONFIRMED", "DENIED", "REVOKED"].includes(value.status)) return null;
  const fields = ["employer_contact", "source_url", "offer_reference", "job_title", "confirmed_at", "recorded_at", "note"] as const;
  if (!fields.every(field => typeof value[field] === "string")) return null;
  if (value.status === "CONFIRMED" && (scamStatus === "CONFIRMED_SCAM" || !value.employer_contact || !value.source_url.startsWith("https://")
      || !value.offer_reference || !value.job_title || entry.independentContact !== true || entry.recruiterConfirmed !== true || entry.termsConfirmed !== true)) return null;
  return { status: value.status, ...Object.fromEntries(fields.map(field => [field, value[field]])) } as OfferConfirmation;
}
