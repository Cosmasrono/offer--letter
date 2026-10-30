import { Icon } from "./Icon";

type Props = { reportId: string; priceKes: number; paymentsReady: boolean; unlocked: boolean; token?: string };

/** ReportView is only rendered after server-side payment verification. The PDF route verifies it again. */
export function DownloadReport({ reportId, unlocked, token = "" }: Props) {
  if (!unlocked) return null;
  const downloadUrl = `/api/report-pdf?id=${reportId}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
  return (
    <section className="card flex flex-col gap-5 p-6 sm:flex-row sm:items-center">
      <span className="feature-icon"><Icon name="file" /></span>
      <div className="min-w-0 flex-1"><h2 className="text-base font-semibold">Your PDF report is included.</h2><p className="muted mt-1 text-sm">A printable copy of your findings and next steps. No extra payment needed.</p></div>
      <a href={downloadUrl} className="btn-primary">Download PDF <Icon name="arrow" className="h-4 w-4" /></a>
    </section>
  );
}
