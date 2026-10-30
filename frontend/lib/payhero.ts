/**
 * PayHero (https://docs.payhero.co.ke) - M-Pesa STK Push and transaction status.
 * Server-only: it uses the API username and password, which must never reach the browser.
 */

function apiBaseUrl() {
  const base = (process.env.PAYHERO_BASE_URL || "https://backend.payhero.co.ke/api/v2").trim().replace(/\/+$/, "");
  return base.endsWith("/api/v2") ? base : `${base}/api/v2`;
}
const MOCK_DELAY_MS = 6000;

export class PayHeroError extends Error {}

export type TransactionStatus = { status: "QUEUED" | "SUCCESS" | "FAILED"; receipt: string | null };

/**
 * Local testing without PayHero or a phone: no STK prompt is sent and the payment succeeds after a few seconds
 * (or fails for phone 0700000000). Never active in production builds.
 */
export const isMockMode = () => process.env.PAYHERO_MOCK === "true" && process.env.NODE_ENV !== "production";

export const isPayHeroConfigured = () =>
  isMockMode() ||
  Boolean(process.env.PAYHERO_API_USERNAME && process.env.PAYHERO_API_PASSWORD &&
    Number.isSafeInteger(Number(process.env.PAYHERO_CHANNEL_ID)) && Number(process.env.PAYHERO_CHANNEL_ID) > 0);

function authHeader() {
  const credentials = `${process.env.PAYHERO_API_USERNAME}:${process.env.PAYHERO_API_PASSWORD}`;
  return `Basic ${Buffer.from(credentials).toString("base64")}`;
}

function callbackUrl() {
  const url = process.env.PAYHERO_CALLBACK_URL;
  if (!url) return undefined; // without a public URL the payment is confirmed by polling the status instead
  let callback: URL;
  try {
    callback = new URL(url);
  } catch {
    throw new PayHeroError("Set APP_URL and PAYHERO_CALLBACK_URL to your public HTTPS address.");
  }
  if (callback.protocol !== "https:" || ["localhost", "127.0.0.1", "[::1]"].includes(callback.hostname)) {
    throw new PayHeroError("PayHero needs a public HTTPS callback URL. Use your deployed site or an HTTPS tunnel.");
  }
  const secret = process.env.PAYHERO_CALLBACK_SECRET;
  if (secret) callback.searchParams.set("secret", secret);
  return callback.toString();
}

/** Sends the M-Pesa PIN prompt to the customer's phone. Returns PayHero's reference for status checks. */
export async function stkPush(input: { amount: number; phone: string; externalReference: string }) {
  if (isMockMode()) {
    const fail = input.phone === "0700000000" ? 1 : 0;
    return { reference: `MOCK-${Date.now()}-${fail}`, checkoutRequestId: null };
  }

  if (!isPayHeroConfigured()) throw new PayHeroError("Set the PayHero API username, password and valid channel ID.");
  const res = await fetch(`${apiBaseUrl()}/payments`, {
    method: "POST",
    signal: AbortSignal.timeout(30_000),
    headers: { Authorization: authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({
      amount: input.amount,
      phone_number: input.phone,
      channel_id: Number(process.env.PAYHERO_CHANNEL_ID),
      provider: "m-pesa",
      external_reference: input.externalReference,
      callback_url: callbackUrl(),
    }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success || !data.reference) {
    console.error("PayHero STK push failed:", res.status, data);
    throw new PayHeroError("The M-Pesa request could not be sent. Check the number and try again.");
  }
  return { reference: String(data.reference), checkoutRequestId: (data.CheckoutRequestID as string) ?? null };
}

/** Asks PayHero whether a payment went through. This is the only source trusted to mark a payment as paid. */
export async function transactionStatus(reference: string): Promise<TransactionStatus> {
  if (isMockMode() && reference.startsWith("MOCK-")) {
    const [, startedAt, fail] = reference.split("-");
    if (Date.now() - Number(startedAt) < MOCK_DELAY_MS) return { status: "QUEUED", receipt: null };
    return fail === "1" ? { status: "FAILED", receipt: null } : { status: "SUCCESS", receipt: `MOCK${startedAt.slice(-6)}` };
  }

  const res = await fetch(`${apiBaseUrl()}/transaction-status?reference=${encodeURIComponent(reference)}`, {
    signal: AbortSignal.timeout(30_000),
    headers: { Authorization: authHeader() },
    cache: "no-store",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data) {
    console.error("PayHero status check failed:", res.status, data);
    throw new PayHeroError("Could not check the payment status.");
  }
  const status = data.status === "SUCCESS" || data.status === "FAILED" ? data.status : "QUEUED";
  return { status, receipt: data.provider_reference || data.third_party_reference || null };
}
