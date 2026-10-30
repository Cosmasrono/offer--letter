import "server-only";
import { headers } from "next/headers";
import { prisma } from "./prisma";

const KEEP_MS = 24 * 60 * 60 * 1000;

/** The caller's IP as reported by the hosting proxy (x-forwarded-for), or "unknown". */
export async function clientIp() {
  const h = await headers();
  return h.get("x-forwarded-for")?.split(",")[0]?.trim() || h.get("x-real-ip") || "unknown";
}

/** True when `key` already has `max` recorded attempts within the last `windowMs`. */
export async function isRateLimited(key: string, max: number, windowMs: number) {
  const count = await prisma.authAttempt.count({ where: { key, createdAt: { gt: new Date(Date.now() - windowMs) } } });
  return count >= max;
}

export async function recordAttempt(...keys: string[]) {
  await prisma.authAttempt.createMany({ data: keys.map((key) => ({ key })) });
  // MongoDB TTL indexes can't be declared in Prisma, so old attempts are tidied up here.
  await prisma.authAttempt.deleteMany({ where: { createdAt: { lt: new Date(Date.now() - KEEP_MS) } } });
}

export async function clearAttempts(key: string) {
  await prisma.authAttempt.deleteMany({ where: { key } });
}
