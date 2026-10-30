import "server-only";
import { createHash, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { cache } from "react";
import { isDatabaseConfigured, prisma } from "./prisma";
import { isReportExpired } from "./privacy-policy";

const COOKIE = "olc_session";
const SESSION_DAYS = 30;

export type CurrentUser = { id: string; email: string; name: string | null; isAdmin: boolean };

const hashToken = (token: string) => createHash("sha256").update(token).digest("hex");

/** Emails in ADMIN_EMAILS (comma-separated) get the admin role when they sign up or sign in. */
export const isAdminEmail = (email: string) =>
  (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean)
    .includes(email.toLowerCase());

/** Signs this browser in. Only call from a Server Action or Route Handler (it sets a cookie). */
export async function createSession(userId: string) {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000);
  await prisma.session.create({ data: { tokenHash: hashToken(token), userId, expiresAt } });
  (await cookies()).set(COOKIE, token, {
    httpOnly: true, // not readable by page scripts
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax", // not sent on cross-site form posts
    path: "/",
    expires: expiresAt,
  });
}

/** Signs this browser out. Only call from a Server Action or Route Handler. */
export async function deleteSession() {
  const store = await cookies();
  const token = store.get(COOKIE)?.value;
  if (token) await prisma.session.deleteMany({ where: { tokenHash: hashToken(token) } });
  store.delete(COOKIE);
}

/**
 * The signed-in user, or null. Reads a cookie, so with Cache Components any component calling it must sit inside a
 * <Suspense> boundary. Cached per request, so several components can call it for one database lookup.
 */
export const getCurrentUser = cache(async (): Promise<CurrentUser | null> => {
  if (!isDatabaseConfigured()) return null;
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return null;
  const session = await prisma.session.findUnique({ where: { tokenHash: hashToken(token) }, include: { user: true } });
  if (!session || session.expiresAt < new Date()) return null;
  const { user } = session;
  return { id: user.id, email: user.email, name: user.name, isAdmin: user.role === "ADMIN" };
});

/** Owners and admins can see a report saved by a signed-in user; reports checked while signed out stay link-only. */
export function canViewReport(report: { userId: string | null; expiresAt?: Date | null }, user: CurrentUser | null) {
  return !isReportExpired(report) && (!report.userId || user?.isAdmin === true || user?.id === report.userId);
}
