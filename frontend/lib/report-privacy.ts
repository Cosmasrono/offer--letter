import "server-only";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { prisma } from "./prisma";
import { MANAGEMENT_COOKIE, MANAGEMENT_TOKEN_PATTERN, isReportExpired } from "./privacy-policy";
import type { CurrentUser } from "./session";

export const hashManagementToken = (token: string) => createHash("sha256").update(token).digest("hex");

export async function managementToken() {
  const previous = (await cookies()).get(MANAGEMENT_COOKIE)?.value ?? "";
  return MANAGEMENT_TOKEN_PATTERN.test(previous) ? previous : randomBytes(32).toString("hex");
}

/** A public report URL, an administrator role or a payment token does not grant deletion rights. */
export async function canManageReport(report: { userId: string | null; managementTokenHash?: string | null }, user: CurrentUser | null) {
  if (report.userId) return Boolean(user && user.id === report.userId);
  const token = (await cookies()).get(MANAGEMENT_COOKIE)?.value ?? "";
  if (!MANAGEMENT_TOKEN_PATTERN.test(token) || !report.managementTokenHash || !MANAGEMENT_TOKEN_PATTERN.test(report.managementTokenHash)) return false;
  return timingSafeEqual(Buffer.from(hashManagementToken(token), "hex"), Buffer.from(report.managementTokenHash, "hex"));
}

let retentionReady: Promise<void> | undefined;

/** Install the TTL index before accepting new scans. No expiry is added to historical reports. */
export async function ensureReportRetention() {
  retentionReady ??= prisma.$runCommandRaw({ createIndexes: "Report", indexes: [
    { key: { expiresAt: 1 }, name: "Report_privacy_expiry", expireAfterSeconds: 0 },
  ] }).then(() => undefined).catch(() => {
    retentionReady = undefined;
    throw new Error("Report retention is unavailable.");
  });
  await retentionReady;
}

export async function deleteOwnReport(id: string, user: CurrentUser | null) {
  const report = await prisma.report.findUnique({ where: { id } });
  if (!report || isReportExpired(report) || !await canManageReport(report, user)) return false;
  // Keep payment bookkeeping and the consumed report ID; neither can restore a deleted report or credit.
  // Deleting the source also removes its matching keys, text fingerprint, consent and review history.
  const result = await prisma.report.deleteMany({ where: { id, userId: report.userId } });
  return result.count === 1;
}
