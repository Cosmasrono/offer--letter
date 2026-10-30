import { timingSafeEqual } from "node:crypto";
import { handlePayHeroCallback } from "@/lib/payments";

const sameSecret = (a: string, b: string) =>
  a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

/** PayHero posts the payment result here (PAYHERO_CALLBACK_URL). */
export async function POST(request: Request) {
  const expected = process.env.PAYHERO_CALLBACK_SECRET;
  const given = new URL(request.url).searchParams.get("secret") ?? "";
  if (expected && !sameSecret(given, expected)) {
    return Response.json({ error: "Forbidden" }, { status: 403 });
  }
  try {
    await handlePayHeroCallback(await request.json().catch(() => null));
  } catch (error) {
    // Still answer 200: the payer's browser keeps polling the status, which recovers from this.
    console.error("PayHero callback could not be processed:", error);
  }
  return Response.json({ ok: true });
}
