import { BACKEND_URL, backendHeaders } from "@/lib/backend";
import { canDownload } from "@/lib/payments";
import { isDatabaseConfigured, prisma } from "@/lib/prisma";
import { isObjectId, toAnalysisReport } from "@/lib/reports";
import { canViewReport, getCurrentUser } from "@/lib/session";

/** The paid PDF of a saved report: GET /api/report-pdf?id=<report id>&token=<download token> (token optional when signed in). */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const id = url.searchParams.get("id") ?? "";
  const token = url.searchParams.get("token") ?? "";
  if (!isObjectId(id) || !isDatabaseConfigured()) return Response.json({ error: "Unknown report." }, { status: 404 });
  const user = await getCurrentUser();
  const saved = await prisma.report.findUnique({ where: { id } });
  if (!saved || !canViewReport(saved, user)) return Response.json({ error: "Unknown report." }, { status: 404 });
  if (!(await canDownload(id, token, user))) {
    return Response.json({ error: "This download link is not valid. Pay for the report to download it." }, { status: 403 });
  }

  const checkedAt = saved.createdAt.toLocaleString("en-GB", {
    timeZone: "Africa/Nairobi", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
  const siteUrl = process.env.PUBLIC_SITE_URL ?? url.origin;

  let pdf: Response;
  try {
    pdf = await fetch(`${BACKEND_URL}/report-pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...backendHeaders() },
      body: JSON.stringify({
        report: toAnalysisReport(saved),
        report_id: id,
        checked_at: `${checkedAt} (Nairobi time)`,
        report_url: `${siteUrl}/report/${id}`,
      }),
    });
  } catch {
    return Response.json({ error: "The report service is not running. Try again shortly." }, { status: 502 });
  }
  if (!pdf.ok) return Response.json({ error: "The PDF could not be created." }, { status: 502 });

  return new Response(await pdf.arrayBuffer(), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="offer-check-report-${id}.pdf"`,
      "Cache-Control": "private, no-store",
    },
  });
}
