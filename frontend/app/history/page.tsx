import { freeReportTesting, hasPaid } from "@/lib/payments";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { RiskBadge } from "@/components/ReportView";
import { isDatabaseConfigured, prisma } from "@/lib/prisma";
import { getCurrentUser } from "@/lib/session";
import type { RiskLevel } from "@/lib/types";
import { Icon } from "@/components/Icon";
import { reportStatus, SCAM_STATUS_LABELS } from "@/lib/scam-status";
import { activeReports } from "@/lib/privacy-policy";

export const metadata: Metadata = { title: "History · Offer Letter Checker" };

async function ReportList({ searchParams }: { searchParams: PageProps<"/history">["searchParams"] }) {
  if (!isDatabaseConfigured()) {
    return <div className="card px-6 py-12 text-center"><span className="feature-icon mx-auto mb-5"><Icon name="file" /></span><h2 className="text-lg font-semibold">Report history is currently unavailable</h2><p className="muted mt-2 text-sm">You can still check an offer. Saved history will be available when report storage is ready.</p><Link href="/#check" className="btn-primary mt-6">Check an offer <Icon name="arrow" className="h-4 w-4" /></Link></div>;
  }
  const user = await getCurrentUser();
  if (!user) {
    return (
      <div className="card mx-auto max-w-lg p-8 text-center">
        <span className="feature-icon mx-auto mb-5"><Icon name="lock" /></span>
        <h2 className="text-lg font-semibold">Sign in to see your history</h2>
        <p className="muted mt-2 text-sm">
          Letters and messages you check while signed in are saved here, private to you, so you can come back to them
          and download their reports on any device.
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Link href="/sign-in?next=/history" className="btn-primary">
            Sign in
          </Link>
          <Link href="/sign-up?next=/history" className="btn-secondary">
            Create account
          </Link>
        </div>
      </div>
    );
  }

  const showAll = user.isAdmin && (await searchParams).all === "1";
  const reports = await prisma.report.findMany({
    where: { AND: [activeReports(), ...(showAll ? [] : [{ userId: user.id }])] },
    orderBy: { createdAt: "desc" },
    take: 100,
    select: {
      id: true, fileName: true, riskLevel: true, score: true, companyName: true, countryName: true, createdAt: true,
      extractionMethod: true, kind: true, userReportedAt: true, scamStatus: true,
    },
  });

  const access = new Set(await Promise.all(reports.map(async (r) =>
    freeReportTesting() || await hasPaid(r.id, user) ? r.id : "")));
  return (
    <div className="space-y-4">
      {user.isAdmin && (
        <div className="inline-flex flex-wrap rounded-xl bg-slate-100 p-1 text-sm dark:bg-slate-900">
          <Link href="/history" className={`rounded-lg px-3 py-1.5 font-medium ${showAll ? "muted" : "bg-white shadow-sm dark:bg-slate-700"}`}>
            My reports
          </Link>
          <Link href="/history?all=1" className={`rounded-lg px-3 py-1.5 font-medium ${showAll ? "bg-white shadow-sm dark:bg-slate-700" : "muted"}`}>
            All reports (admin)
          </Link>
          <Link href="/admin/verification" className="rounded-lg px-3 py-1.5 font-medium">Verification sources</Link>
          <Link href="/admin/scams" className="rounded-lg px-3 py-1.5 font-medium">Scam review</Link>
        </div>
      )}

      {reports.length === 0 ? (
        <div className="card p-10 text-center">
          <span className="feature-icon mx-auto mb-5"><Icon name="file" /></span>
          <p className="font-medium">No letters checked yet</p>
          <p className="muted mt-1 text-sm">Check an offer letter or job ad and it will appear here.</p>
          <Link href="/" className="btn-primary mt-5">
            Check a letter
          </Link>
        </div>
      ) : (
        <ul className="card divide-y divide-slate-200 overflow-hidden dark:divide-slate-800">
          {reports.map((r) => {
            const notChecked = r.extractionMethod.endsWith("none");
            const locked = !access.has(r.id);
            return (
              <li key={r.id}>
                <Link href={`/report/${r.id}`} className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/60">
                  {/* No text was read (e.g. a scan without OCR), so the letter was never really checked. */}
                  <span className="w-24 shrink-0">
                    {locked ? <span className="text-xs font-semibold">REPORT READY</span> : notChecked ? (
                      <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        NOT CHECKED
                      </span>
                    ) : (
                      <RiskBadge level={r.riskLevel as RiskLevel} />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">
                      {locked ? r.fileName : r.companyName ?? (r.kind === "message" ? "Job ad or message" : r.fileName)}
                    </p>
                    <p className="muted truncate text-sm">
                      {[r.kind === "visa" ? "Visa / permit" : r.kind === "message" ? "Message" : "Letter", !locked && r.countryName, !locked && SCAM_STATUS_LABELS[reportStatus(r)]]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="shrink-0 text-right text-sm">
                    {!locked && !notChecked && <p className="font-semibold tabular-nums">{r.score}/100</p>}
                    <p className="muted text-xs">{r.createdAt.toLocaleDateString("en-GB", { timeZone: "Africa/Nairobi" })}</p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function HistoryPage({ searchParams }: PageProps<"/history">) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-5 pb-3">
        <div><p className="eyebrow">Your account</p>
        <h1 className="mt-3 text-3xl font-medium tracking-tight sm:text-4xl">Your checks, all together.</h1>
        <p className="muted mt-3 text-sm">Revisit the details. Pick up where you left off.</p></div>
        <Link href="/#check" className="btn-secondary">Check another offer <Icon name="plus" className="h-4 w-4" /></Link>
      </div>
      <Suspense fallback={<div className="card h-64 animate-pulse" />}>
        <ReportList searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
