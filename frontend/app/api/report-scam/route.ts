import { isDatabaseConfigured } from "@/lib/prisma";
import { isObjectId, reportAsScam } from "@/lib/reports";
import { getCurrentUser } from "@/lib/session";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const id = typeof body?.id === "string" ? body.id : "";
  if (!isObjectId(id)) {
    return Response.json({ error: "Unknown report." }, { status: 400 });
  }
  if (!isDatabaseConfigured()) {
    return Response.json({ error: "Reports can't be saved because no database is configured." }, { status: 503 });
  }

  const result = await reportAsScam(id, await getCurrentUser());
  if (result === "missing") {
    return Response.json({ error: "This report no longer exists." }, { status: 404 });
  }
  return Response.json({ status: result });
}
