import { isDatabaseConfigured, prisma } from "@/lib/prisma";
import { isObjectId, reviewScam, ReviewConflict } from "@/lib/reports";
import { reportStatus } from "@/lib/scam-status";
import { getCurrentUser } from "@/lib/session";

export async function GET(request: Request) {
  if (!(await getCurrentUser())?.isAdmin) return Response.json({ error: "Administrator access required." }, { status: 403 });
  if (!isDatabaseConfigured()) return Response.json({ error: "Report storage is unavailable." }, { status: 503 });
  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!isObjectId(id)) return Response.json({ error: "Unknown report." }, { status: 400 });
  const report = await prisma.report.findUnique({ where: { id }, select: { scamStatus: true, riskLevel: true, userReportedAt: true, reviewHistory: true } });
  if (!report) return Response.json({ error: "Unknown report." }, { status: 404 });
  return Response.json({ scamStatus: reportStatus(report), history: report.reviewHistory ?? [] }, { headers: { "Cache-Control": "private, no-store" } });
}

export async function POST(request: Request) {
  const user = await getCurrentUser();
  if (!user?.isAdmin) return Response.json({ error: "Administrator access required." }, { status: 403 });
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  if (!isDatabaseConfigured()) return Response.json({ error: "Report storage is unavailable." }, { status: 503 });
  const body = await request.json().catch(() => null);
  const id = typeof body?.id === "string" ? body.id : "";
  const action = body?.action;
  const note = typeof body?.note === "string" ? body.note.trim() : "";
  if (!isObjectId(id) || !["CONFIRM_SCAM", "CLEAR", "REOPEN"].includes(action) || note.length < 20 || note.length > 2000) {
    return Response.json({ error: "Choose a report and action, and explain the decision in 20–2000 characters." }, { status: 400 });
  }
  let sourceUrl: string | null = null;
  if (body.sourceUrl) {
    try {
      const source = new URL(body.sourceUrl);
      if (source.protocol !== "https:" || source.username || source.password || source.href.length > 1000) throw new Error();
      sourceUrl = source.href;
    } catch { return Response.json({ error: "Use a valid HTTPS source URL without embedded credentials." }, { status: 400 }); }
  }
  try {
    const result = await reviewScam(id, action, note, sourceUrl, user);
    if (!result) return Response.json({ error: "Unknown report." }, { status: 404 });
    return Response.json(result, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof ReviewConflict ? error.message : "The decision could not be saved. Please retry." }, { status: error instanceof ReviewConflict ? 409 : 503 });
  }
}
