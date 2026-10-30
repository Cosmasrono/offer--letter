import { isDatabaseConfigured } from "@/lib/prisma";
import { isObjectId } from "@/lib/reports";
import { getCurrentUser } from "@/lib/session";
import { deleteOwnReport } from "@/lib/report-privacy";

export async function DELETE(request: Request) {
  if (request.headers.get("origin") !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  if (!isDatabaseConfigured()) return Response.json({ error: "Report storage is unavailable." }, { status: 503 });
  const body = await request.json().catch(() => null);
  const id = typeof body?.id === "string" ? body.id : "";
  if (!isObjectId(id)) return Response.json({ error: "Unknown report." }, { status: 404 });
  try {
    if (!await deleteOwnReport(id, await getCurrentUser())) return Response.json({ error: "Report not found or deletion is not permitted in this browser." }, { status: 404 });
    return Response.json({ deleted: true }, { headers: { "Cache-Control": "private, no-store" } });
  } catch {
    return Response.json({ error: "The report could not be deleted. Please try again." }, { status: 503 });
  }
}
