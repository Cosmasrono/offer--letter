import { canDownload } from "@/lib/payments";
import { isDatabaseConfigured } from "@/lib/prisma";
import { isObjectId } from "@/lib/reports";
import { getCurrentUser } from "@/lib/session";
import { ConfirmationConflict, ConfirmationInputError, recordOfferConfirmation } from "@/lib/record-offer-confirmation";

export async function POST(request: Request) {
  const user = await getCurrentUser();
  if (!user?.isAdmin) return Response.json({ error: "Administrator access required." }, { status: 403 });
  if (request.headers.get("origin") !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  if (!isDatabaseConfigured()) return Response.json({ error: "Report storage is unavailable." }, { status: 503 });
  const body = await request.json().catch(() => null);
  const id = typeof body?.id === "string" ? body.id : "";
  if (!isObjectId(id)) return Response.json({ error: "Unknown report." }, { status: 400 });
  if (!await canDownload(id, typeof body.token === "string" ? body.token : "", user)) return Response.json({ error: "Open an unlocked report before recording employer confirmation." }, { status: 403 });
  try {
    const confirmation = await recordOfferConfirmation(id, body, user);
    if (!confirmation) return Response.json({ error: "Unknown report." }, { status: 404 });
    return Response.json({ confirmation }, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    const status = error instanceof ConfirmationInputError ? 400 : error instanceof ConfirmationConflict ? 409 : 503;
    return Response.json({ error: status === 503 ? "Confirmation could not be saved. Please retry." : (error as Error).message }, { status });
  }
}
