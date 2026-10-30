"use server";

import { redirect } from "next/navigation";
import { burnPasswordCheck, hashPassword, verifyPassword } from "./password";
import { isDatabaseConfigured, prisma } from "./prisma";
import { clearAttempts, clientIp, isRateLimited, recordAttempt } from "./rate-limit";
import { createSession, deleteSession, isAdminEmail } from "./session";

export type AuthFormState = { error?: string; email?: string; name?: string } | undefined;

const MIN_PASSWORD = 10;
const MAX_PASSWORD = 128;
const FIFTEEN_MINUTES = 15 * 60 * 1000;
const ONE_HOUR = 60 * 60 * 1000;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Only same-site paths, so a crafted ?next= link can't send people to another website after signing in. */
function safeNext(value: FormDataEntryValue | null) {
  const next = typeof value === "string" ? value : "";
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

function read(formData: FormData) {
  return {
    email: String(formData.get("email") ?? "").trim().toLowerCase(),
    password: String(formData.get("password") ?? ""),
    name: String(formData.get("name") ?? "").trim().slice(0, 80),
    next: safeNext(formData.get("next")),
  };
}

export async function signUp(_state: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const { email, password, name, next } = read(formData);
  if (!isDatabaseConfigured()) return { error: "Accounts need a database, and none is configured.", email, name };
  if (!EMAIL_RE.test(email) || email.length > 200) return { error: "Enter a valid email address.", email, name };
  if (password.length < MIN_PASSWORD) return { error: `Use at least ${MIN_PASSWORD} characters for your password.`, email, name };
  if (password.length > MAX_PASSWORD) return { error: `Use at most ${MAX_PASSWORD} characters for your password.`, email, name };
  if (password.toLowerCase().includes(email.split("@")[0]) && email.split("@")[0].length >= 4) {
    return { error: "Your password shouldn't contain your email name.", email, name };
  }

  const ipKey = `signup-ip:${await clientIp()}`;
  // Generous, because many people share one network (cyber cafes, offices, mobile carrier NAT).
  if (await isRateLimited(ipKey, 20, ONE_HOUR)) {
    return { error: "Too many accounts were created from this network. Try again in an hour.", email, name };
  }
  await recordAttempt(ipKey);

  if (await prisma.user.findUnique({ where: { email }, select: { id: true } })) {
    return { error: "An account with this email already exists. Sign in instead.", email, name };
  }
  const user = await prisma.user.create({
    data: { email, name: name || null, passwordHash: await hashPassword(password), role: isAdminEmail(email) ? "ADMIN" : "USER" },
  });
  await createSession(user.id);
  redirect(next);
}

export async function signIn(_state: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const { email, password, next } = read(formData);
  if (!isDatabaseConfigured()) return { error: "Accounts need a database, and none is configured.", email };
  if (!email || !password) return { error: "Enter your email and password.", email };

  const emailKey = `signin-email:${email}`;
  const ipKey = `signin-ip:${await clientIp()}`;
  if ((await isRateLimited(emailKey, 5, FIFTEEN_MINUTES)) || (await isRateLimited(ipKey, 20, FIFTEEN_MINUTES))) {
    return { error: "Too many failed sign-in attempts. Wait 15 minutes and try again.", email };
  }

  const user = await prisma.user.findUnique({ where: { email } });
  const valid = user?.passwordHash ? await verifyPassword(password, user.passwordHash) : (await burnPasswordCheck(password), false);
  if (!user || !valid) {
    await recordAttempt(emailKey, ipKey);
    // Same message either way, so the form doesn't reveal which emails have accounts.
    return { error: "Email or password is incorrect.", email };
  }

  await clearAttempts(emailKey);
  const role = isAdminEmail(email) ? "ADMIN" : "USER";
  if (user.role !== role) await prisma.user.update({ where: { id: user.id }, data: { role } });
  await createSession(user.id);
  redirect(next);
}

export async function signOut() {
  await deleteSession();
  redirect("/");
}
