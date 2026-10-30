/** Change this version whenever the purposes, providers or retention notice changes. */
export const CONSENT_VERSION = "2026-10-29";
export const REPORT_RETENTION_DAYS = 30;
export const MANAGEMENT_COOKIE = "olc_report_management";
export const MANAGEMENT_TOKEN_PATTERN = /^[a-f0-9]{64}$/;

export type ReportPrivacy = {
  consentVersion: string;
  consentedAt: Date;
  memoryConsent: boolean;
  managementTokenHash: string;
  expiresAt: Date;
};

export function readConsent(form: FormData) {
  if (form.get("consentVersion") !== CONSENT_VERSION || form.get("processingConsent") !== "true" || form.get("submissionAuthority") !== "true") return null;
  return { version: CONSENT_VERSION, memoryConsent: form.get("memoryConsent") === "true" };
}

export function reportExpiry(now = new Date()) {
  return new Date(now.getTime() + REPORT_RETENTION_DAYS * 24 * 60 * 60 * 1000);
}

/** Older reports without an expiry retain their existing behaviour. */
export function isReportExpired(report: { expiresAt?: Date | null }, now = new Date()) {
  return Boolean(report.expiresAt && report.expiresAt.getTime() <= now.getTime());
}

/** MongoDB distinguishes missing fields from null, so include both for legacy reports. */
export function activeReports(now = new Date()) {
  return { OR: [{ expiresAt: { gt: now } }, { expiresAt: null }, { expiresAt: { isSet: false } }] };
}
