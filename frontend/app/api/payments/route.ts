import { checkPayment, PaymentError, startPayment } from "@/lib/payments";
import { isDatabaseConfigured } from "@/lib/prisma";
import { isObjectId } from "@/lib/reports";
import { getCurrentUser } from "@/lib/session";

/**
 * Sends the M-Pesa prompt.
 * Body { reportId, phone }: unlock a completed scan's findings and PDF.
 */
export async function POST(request: Request) {
  if (!isDatabaseConfigured()) {
    return Response.json({ error: "Payments need a database, and none is configured." }, { status: 503 });
  }
  const body = await request.json().catch(() => null);
  const reportId = typeof body?.reportId === "string" ? body.reportId : "";
  const phone = typeof body?.phone === "string" ? body.phone : "";
  if (!isObjectId(reportId)) return Response.json({ error: "Unknown report." }, { status: 400 });

  try {
    const user = await getCurrentUser();
    return Response.json(await startPayment(reportId, phone, user), { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (error instanceof PaymentError) return Response.json({ error: error.message }, { status: 400 });
    throw error;
  }
}

/** Where a payment stands: GET /api/payments?id=... The download token is only returned once it is paid. */
export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!isObjectId(id) || !isDatabaseConfigured()) return Response.json({ error: "Unknown payment." }, { status: 404 });
  const state = await checkPayment(id);
  if (!state) return Response.json({ error: "Unknown payment." }, { status: 404 });
  return Response.json(state, { headers: { "Cache-Control": "private, no-store" } });
}
