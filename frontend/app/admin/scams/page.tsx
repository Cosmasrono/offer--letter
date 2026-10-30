import Link from "next/link";
import { Suspense } from "react";
import { ScamReviewQueue } from "@/components/ScamReviewQueue";
import { prisma, isDatabaseConfigured } from "@/lib/prisma";
import { getCurrentUser } from "@/lib/session";
import { reportStatus } from "@/lib/scam-status";
import { activeReports } from "@/lib/privacy-policy";

async function Queue({ searchParams }: { searchParams: PageProps<"/admin/scams">["searchParams"] }) {
  const user = await getCurrentUser();
  if (!user?.isAdmin) return <div className="card p-6"><h2 className="font-semibold">Administrator access required</h2><Link href="/sign-in?next=/admin/scams" className="btn-primary mt-4">Sign in</Link></div>;
  if (!isDatabaseConfigured()) return <p>Report storage is unavailable.</p>;
  const filter = (await searchParams).status;
  const where = filter === "confirmed" ? { scamStatus: "CONFIRMED_SCAM" } : filter === "cleared" ? { scamStatus: "CLEARED" }
    : { scamStatus: { in: ["REPORTED_SCAM", "SUSPECTED_SCAM"] } };
  const reports = await prisma.report.findMany({ where: { AND: [where, activeReports()] }, orderBy: { createdAt: "desc" }, take: 100,
    select: { id: true, fileName: true, scamStatus: true, riskLevel: true, userReportedAt: true, createdAt: true, reviewNote: true } });
  return <div className="space-y-5"><nav className="flex flex-wrap gap-4 text-sm" aria-label="Review status"><Link href="/admin/scams" className="underline">Awaiting review</Link><Link href="/admin/scams?status=confirmed" className="underline">Confirmed scams</Link><Link href="/admin/scams?status=cleared" className="underline">Dismissed cases</Link></nav><ScamReviewQueue reports={reports.map(report => ({ id: report.id, fileName: report.fileName, reviewNote: report.reviewNote, scamStatus: reportStatus(report), createdAt: report.createdAt.toISOString() }))} /></div>;
}

export default function ScamReviewPage({ searchParams }: PageProps<"/admin/scams">) {
  return <div className="mx-auto max-w-3xl space-y-6"><Link href="/history" className="text-sm underline">← History</Link><div><p className="eyebrow">Administration</p><h1 className="text-3xl font-semibold">Scam cases and feedback</h1></div><Suspense fallback={<p>Loading review queue…</p>}><Queue searchParams={searchParams} /></Suspense></div>;
}
