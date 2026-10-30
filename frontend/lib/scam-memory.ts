import { createHash } from "node:crypto";
import type { Entities, Fingerprint } from "./types";

const FREE_EMAILS = new Set(["gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "gmx.com", "gmx.net", "mail.com", "yandex.com", "yandex.ru", "zoho.com", "rediffmail.com", "inbox.com"]);

export function normalizePhone(value: string) {
  let digits = value.replace(/\D/g, "");
  if (digits.startsWith("00")) digits = digits.slice(2);
  if (/^0[17]\d{8}$/.test(digits)) digits = `254${digits.slice(1)}`;
  if (/^[17]\d{8}$/.test(digits)) digits = `254${digits}`;
  return digits;
}

/** Names/domains and shared paybills copied into fake letters must not become global blacklists. */
export function memoryKeys(entities: Partial<Entities>): string[] {
  return [...new Set([
    ...(entities.emails ?? []).filter(email => FREE_EMAILS.has(email.split("@")[1]?.toLowerCase())).map(email => `EMAIL:${email.trim().toLowerCase()}`),
    ...(entities.phones ?? []).map(phone => normalizePhone(phone)).filter(phone => phone.length >= 9).map(phone => `PHONE:${phone}`),
    ...(entities.payment_accounts ?? []).map(value => value.normalize("NFKC").trim().toLowerCase().replace(/\s+/g, " "))
      .filter(value => value && !/^paybill \d+$/.test(value)).map(value => `PAYMENT:${value}`),
  ])].sort();
}

export function validFingerprint(value: unknown): Fingerprint | null {
  if (!value || typeof value !== "object") return null;
  const fingerprint = value as Fingerprint;
  if (!Array.isArray(fingerprint.signature) || fingerprint.signature.length !== 64 || !fingerprint.signature.every(Number.isSafeInteger)
    || !Array.isArray(fingerprint.bands) || !fingerprint.bands.every(band => typeof band === "string")) return null;
  return fingerprint;
}

export function similarity(a: Fingerprint | null, b: Fingerprint | null) {
  return a && b ? a.signature.filter((value, i) => value === b.signature[i]).length / 64 : 0;
}

/** Repeated uploads of identical wording count as one pattern, not independent confirmations. */
export function patternGroup(fingerprint: Fingerprint | null, keys: string[]) {
  return createHash("sha256").update(fingerprint ? fingerprint.signature.join(",") : keys.join("|")).digest("hex");
}
