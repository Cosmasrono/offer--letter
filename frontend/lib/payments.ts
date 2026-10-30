import { randomBytes, timingSafeEqual } from "node:crypto";
import { PayHeroError, isPayHeroConfigured, stkPush, transactionStatus } from "./payhero";
import { prisma } from "./prisma";
import { canViewReport, type CurrentUser } from "./session";
import { isReportExpired } from "./privacy-policy";

/** An explicit local development override; ignored by builds and production servers. */
export const freeReportTesting = () => process.env.NODE_ENV === "development" && process.env.FREE_REPORT_TESTING === "true";

/** Missing/invalid prices fall back to KES 50. Only the explicit development override enables free access. */
export const reportPriceKes = () => {
  if (freeReportTesting()) return 0;
  const configured = Number(process.env.REPORT_PRICE_KES);
  return Number.isFinite(configured) && configured > 0 ? Math.max(1, Math.round(configured)) : 50;
};
export const paymentsReady = () => isPayHeroConfigured();

const STATUS_CHECK_INTERVAL_MS = 3000;
const GIVE_UP_AFTER_MS = 3 * 60 * 1000; // M-Pesa prompts expire after about a minute
// PayHero blocks a phone for 24 hours after 10 failed/cancelled prompts in a row, so stop well before that.
const MAX_UNPAID_ATTEMPTS = 3;
const ATTEMPT_WINDOW_MS = 15 * 60 * 1000;

export class PaymentError extends Error {}

export type PaymentState = {
  status: "PENDING" | "SUCCESS" | "FAILED";
  downloadToken?: string;
  receipt?: string | null;
  message?: string;
  // Paid-before-checking credits only: whether it can still pay for a check, and the report it paid for.
  available?: boolean;
  reportId?: string | null;
};

/** "0712 345 678", "+254712345678", "254712345678" or "712345678" -> "0712345678". */
export function normalizeKenyanPhone(input: string): string | null {
  const digits = input.replace(/[\s()+-]/g, "");
  const m = digits.match(/^(?:254|0)?([17]\d{8})$/);
  return m ? `0${m[1]}` : null;
}

const newToken = () => randomBytes(24).toString("hex");

/** Starts an M-Pesa payment for a completed scan's findings and PDF. */
export async function startPayment(
  reportId: string,
  phoneInput: string,
  user: CurrentUser | null,
): Promise<{ paymentId: string } & PaymentState> {
  if (freeReportTesting()) throw new PaymentError("Free testing is enabled. Open the report directly; no payment is needed.");
  const report = await prisma.report.findUnique({ where: { id: reportId }, select: { id: true, userId: true } });
  if (!report || !canViewReport(report, user)) throw new PaymentError("This report no longer exists.");
  const userId = user?.id ?? null;

  const amount = reportPriceKes();
  return sendPrompt({ purpose: "REPORT", reportId, userId, phoneInput, amount, reference: `OLC-${reportId}` });
}

async function sendPrompt(input: {
  purpose: "CHECK" | "REPORT";
  reportId: string | null;
  userId: string | null;
  phoneInput: string;
  amount: number;
  reference: string;
}): Promise<{ paymentId: string } & PaymentState> {
  const { purpose, reportId, userId, amount } = input;
  if (!isPayHeroConfigured()) throw new PaymentError("M-Pesa payments are not set up on this site yet.");

  const phone = normalizeKenyanPhone(input.phoneInput);
  if (!phone) throw new PaymentError("Enter a Safaricom number like 0712 345 678.");

  const recentUnpaid = await prisma.payment.count({
    where: { phone, status: { not: "SUCCESS" }, createdAt: { gt: new Date(Date.now() - ATTEMPT_WINDOW_MS) } },
  });
  if (recentUnpaid >= MAX_UNPAID_ATTEMPTS) {
    throw new PaymentError("Too many unfinished payment attempts for this number. Please wait 15 minutes and try again.");
  }

  const payment = await prisma.payment.create({
    data: { purpose, reportId, userId, phone, amount, status: "PENDING", externalReference: `${input.reference}-${randomBytes(4).toString("hex")}` },
  });
  try {
    const { reference, checkoutRequestId } = await stkPush({ amount, phone, externalReference: payment.externalReference });
    await prisma.payment.update({ where: { id: payment.id }, data: { providerReference: reference, checkoutRequestId } });
  } catch (error) {
    const message = error instanceof PayHeroError ? error.message : "The M-Pesa request could not be sent.";
    await prisma.payment.update({ where: { id: payment.id }, data: { status: "FAILED", failureReason: message } });
    throw new PaymentError(message);
  }
  return { paymentId: payment.id, status: "PENDING" };
}

async function markPaid(paymentId: string, receipt: string | null) {
  // Conditional so a callback and a status check arriving together can't both hand out tokens.
  await prisma.payment.updateMany({
    where: { id: paymentId, status: { not: "SUCCESS" } },
    data: { status: "SUCCESS", mpesaReceipt: receipt, downloadToken: newToken(), failureReason: null },
  });
}

/** Re-checks a pending payment with PayHero (at most every few seconds) and returns where it stands. */
export async function checkPayment(paymentId: string): Promise<PaymentState | null> {
  let payment = await prisma.payment.findUnique({ where: { id: paymentId } });
  if (!payment) return null;

  const due = !payment.lastCheckedAt || Date.now() - payment.lastCheckedAt.getTime() > STATUS_CHECK_INTERVAL_MS;
  if (payment.status === "PENDING" && payment.providerReference && due) {
    await prisma.payment.update({ where: { id: payment.id }, data: { lastCheckedAt: new Date() } });
    try {
      const result = await transactionStatus(payment.providerReference);
      if (result.status === "SUCCESS") await markPaid(payment.id, result.receipt);
      else if (result.status === "FAILED") {
        await prisma.payment.update({
          where: { id: payment.id },
          data: { status: "FAILED", failureReason: "The payment was cancelled or did not go through." },
        });
      }
    } catch (error) {
      // A failed status check is retried on the next poll.
      console.error("Payment status check failed:", error);
    }
    payment = (await prisma.payment.findUnique({ where: { id: paymentId } }))!;
  }

  if (payment.status === "PENDING" && Date.now() - payment.createdAt.getTime() > GIVE_UP_AFTER_MS) {
    const failureReason = "No payment was received. The M-Pesa prompt may have expired - please try again.";
    await prisma.payment.updateMany({ where: { id: payment.id, status: "PENDING" }, data: { status: "FAILED", failureReason } });
    return { status: "FAILED", message: failureReason };
  }
  if (payment.status === "SUCCESS") {
    const credit = payment.purpose === "CHECK" ? { available: !payment.reportId, reportId: payment.reportId } : {};
    return { status: "SUCCESS", downloadToken: payment.downloadToken!, receipt: payment.mpesaReceipt, ...credit };
  }
  return { status: payment.status as PaymentState["status"], message: payment.failureReason ?? undefined };
}

/**
 * PayHero's callback. Its body is not signed, so it is only used to find the payment; whether it was paid is
 * confirmed with PayHero's status API before anything is unlocked.
 */
export async function handlePayHeroCallback(body: unknown) {
  const response = (body as { response?: Record<string, unknown> } | null)?.response ?? {};
  const externalReference = typeof response.ExternalReference === "string" ? response.ExternalReference : null;
  const checkoutRequestId = typeof response.CheckoutRequestID === "string" ? response.CheckoutRequestID : null;
  if (!externalReference && !checkoutRequestId) return;

  const payment = await prisma.payment.findFirst({
    where: externalReference ? { externalReference } : { checkoutRequestId },
  });
  if (!payment?.providerReference || payment.status === "SUCCESS") return;

  const result = await transactionStatus(payment.providerReference);
  // A late payment can still succeed after we gave up waiting, so FAILED payments may be upgraded here.
  if (result.status === "SUCCESS") await markPaid(payment.id, result.receipt);
  else if (result.status === "FAILED" && payment.status === "PENDING") {
    await prisma.payment.update({
      where: { id: payment.id },
      data: { status: "FAILED", failureReason: "The payment was cancelled or did not go through." },
    });
  }
}

/**
 * Whether this browser may download the report's PDF: with the token from a completed payment, as a signed-in user
 * who paid for it (on any device). Account roles never bypass payment.
 */
export async function canDownload(reportId: string, token: string, user: CurrentUser | null) {
  const report = await prisma.report.findUnique({ where: { id: reportId }, select: { expiresAt: true } });
  if (!report || isReportExpired(report)) return false;
  if (freeReportTesting()) return true;
  if (/^[a-f0-9]{48}$/.test(token)) {
    if (await prisma.payment.findFirst({ where: { reportId, downloadToken: token, status: "SUCCESS", amount: { gt: 0 } }, select: { id: true } })) return true;
  }
  return user ? hasPaid(reportId, user) : false;
}

/** A signed-in user has a completed payment for this report. */
export async function hasPaid(reportId: string, user: CurrentUser) {
  return Boolean(await prisma.payment.findFirst({ where: { reportId, userId: user.id, status: "SUCCESS", amount: { gt: 0 } }, select: { id: true } }));
}

const sameToken = (a: string, b: string) =>
  a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

/**
 * A paid, still-unused check credit (pay-first), if this browser holds its token or it belongs to the signed-in
 * user. Returns null otherwise, including once a check has used it.
 */
export async function findCheckCredit(paymentId: string, token: string, user: CurrentUser | null) {
  if (!/^[a-f0-9]{24}$/i.test(paymentId)) return null;
  const payment = await prisma.payment.findFirst({
    where: { id: paymentId, purpose: "CHECK", status: "SUCCESS", reportId: null, amount: { gt: 0 } },
    select: { id: true, userId: true, downloadToken: true },
  });
  if (!payment?.downloadToken) return null;
  const holdsToken = /^[a-f0-9]{48}$/.test(token) && sameToken(token, payment.downloadToken);
  const owns = Boolean(user && payment.userId === user.id);
  return holdsToken || owns ? { id: payment.id, token: payment.downloadToken } : null;
}

/**
 * Uses up a check credit for the report its check produced. Conditional, so one credit can't pay for two checks
 * started at the same time; returns false if another check used it first.
 */
export async function spendCheckCredit(paymentId: string, reportId: string) {
  const { count } = await prisma.payment.updateMany({
    where: { id: paymentId, purpose: "CHECK", status: "SUCCESS", reportId: null },
    data: { reportId },
  });
  return count === 1;
}
