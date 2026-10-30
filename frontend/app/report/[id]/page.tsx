import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ReportView } from "@/components/ReportView";
import { OfferConfirmationForm } from "@/components/OfferConfirmationForm";
import { canDownload, paymentsReady, reportPriceKes } from "@/lib/payments";
import { ReportPayment } from "@/components/ReportPayment";
import { isDatabaseConfigured, prisma } from "@/lib/prisma";
import { isObjectId, toAnalysisReport } from "@/lib/reports";
import { canViewReport, getCurrentUser } from "@/lib/session";
import { ReportPrivacy } from "@/components/ReportPrivacy";
import { RecentReports, RememberReportRisk } from "@/components/RecentReports";
import type { RiskLevel } from "@/lib/types";
import { UploadForm } from "@/components/UploadForm";
import { canManageReport } from "@/lib/report-privacy";
import { isReportExpired } from "@/lib/privacy-policy";

async function SavedReport({ params, searchParams }: PageProps<"/report/[id]">) {
  const { id } = await params;
  if (!isObjectId(id) || !isDatabaseConfigured()) notFound();
  const [report, user] = await Promise.all([prisma.report.findUnique({ where: { id } }), getCurrentUser()]);
  if (!report || isReportExpired(report)) notFound();

  if (!canViewReport(report, user)) {
    // A signed-in user's report is private. Ask a signed-out visitor to sign in; to anyone else it doesn't exist.
    if (user) notFound();
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <h1 className="text-xl font-bold">This report is private</h1>
        <p className="muted mt-2 text-sm">It belongs to an account. Sign in as its owner to see it.</p>
        <Link href={`/sign-in?next=${encodeURIComponent(`/report/${id}`)}`} className="btn-primary mt-6">
          Sign in
        </Link>
      </div>
    );
  }

  const query = await searchParams;
  const token = typeof query.token === "string" ? query.token : "";
  const unlocked = await canDownload(id, token, user);
  const privacy = <ReportPrivacy id={id} expiresAt={report.expiresAt?.toISOString() ?? null} canDelete={await canManageReport(report, user)} />;
  if (!unlocked) return <><ReportPayment reportId={id} priceKes={reportPriceKes()} paymentsReady={paymentsReady()} attemptedToken={token} />{privacy}</>;
  return (
    <>
    <ReportView
      report={toAnalysisReport(report)}
      saved={{
        id,
        userReported: Boolean(report.userReportedAt),
        priceKes: reportPriceKes(),
        paymentsReady: paymentsReady(),
        unlocked,
        // A confirmed payment's token unlocks both the findings and PDF.
        token: /^[a-f0-9]{48}$/.test(token) ? token : undefined,
        checkedAt: report.createdAt.toLocaleString("en-GB", {
          timeZone: "Africa/Nairobi", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
        }),
      }}
    />
    <RememberReportRisk id={id} risk={report.riskLevel as RiskLevel} />
    {user?.isAdmin && report.kind !== "visa" && <OfferConfirmationForm reportId={id} token={token} />}
    {privacy}
    </>
  );
}

export default function ReportPage({ params, searchParams }: PageProps<"/report/[id]">) {
  return (
    <div className="space-y-6">
      <a href="#check-another" className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100">
        <span aria-hidden>↓</span> Check another letter or message
      </a>
      <Suspense fallback={<ReportSkeleton />}>
        <SavedReport params={params} searchParams={searchParams} />
      </Suspense>
      <Suspense>
        <CheckAnother params={params} />
      </Suspense>
    </div>
  );
}

// Check the next letter here, without leaving this report; earlier checks stay listed below the form.
async function CheckAnother({ params }: { params: PageProps<"/report/[id]">["params"] }) {
  const { id } = await params;
  return (
    <section id="check-another" className="grid scroll-mt-6 gap-6 lg:grid-cols-2" aria-label="Check another letter or message">
      {/* Keyed by report so the form starts fresh after each scan opens a new report. */}
      <div className="checker-column"><UploadForm key={id} priceKes={reportPriceKes()} /></div>
      <RecentReports currentId={id} />
    </section>
  );
}

function ReportSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading report">
      <div className="card h-56 animate-pulse" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card h-80 animate-pulse lg:col-span-2" />
        <div className="card h-80 animate-pulse" />
      </div>
    </div>
  );
}
