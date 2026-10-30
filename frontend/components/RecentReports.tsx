"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { forgetReport, RECENT_REPORTS_EVENT, recentReports, setReportRisk, type RecentReport } from "@/lib/recent-reports";
import type { RiskLevel } from "@/lib/types";
import { Icon } from "./Icon";

// Same colours as ReportView's RiskBadge, without pulling the whole report view into the browser bundle.
const RISK_STYLES: Record<RiskLevel, string> = {
  HIGH: "bg-red-600 text-white",
  MEDIUM: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  LOW: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
};

/** Rendered with unlocked findings so the recent list can show their risk level. */
export function RememberReportRisk({ id, risk }: { id: string; risk: RiskLevel }) {
  useEffect(() => setReportRisk(id, risk), [id, risk]);
  return null;
}

/** Reports checked in this browser, newest first. Renders nothing until there is one. */
export function RecentReports({ currentId }: { currentId?: string }) {
  const [reports, setReports] = useState<RecentReport[]>([]);

  useEffect(() => {
    const refresh = () => setReports(recentReports());
    refresh();
    window.addEventListener(RECENT_REPORTS_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(RECENT_REPORTS_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  if (reports.length === 0) return null;
  return (
    <section className="card p-5" aria-labelledby="recent-reports-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="recent-reports-title" className="text-base font-semibold">Your recent checks</h2>
        <span className="muted text-xs">Saved in this browser</span>
      </div>
      <ul className="mt-3 divide-y divide-slate-200 dark:divide-slate-800">
        {reports.map((report) => {
          const current = report.id === currentId;
          let token = "";
          try { token = localStorage.getItem(`olc-report-download-${report.id}`) ?? ""; } catch { /* Optional browser storage. */ }
          return (
            <li key={report.id} className="flex items-center gap-3 py-2.5 text-sm">
              <Icon name="file" className="h-4 w-4 shrink-0 text-slate-500" />
              <div className="min-w-0 flex-1">
                {current ? <span className="block truncate font-medium">{report.name} <span className="muted font-normal">· viewing</span></span>
                  : <Link href={`/report/${report.id}${token ? `?token=${encodeURIComponent(token)}` : ""}`} className="block truncate font-medium underline-offset-2 hover:underline">{report.name}</Link>}
                <span className="muted text-xs">{report.kind === "message" ? "Job ad or message" : "Offer letter"} · {new Date(report.checkedAt).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
              </div>
              {report.risk && RISK_STYLES[report.risk] && <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${RISK_STYLES[report.risk]}`}>{report.risk}</span>}
              <button type="button" className="muted text-xs underline" onClick={() => forgetReport(report.id)} aria-label={`Remove ${report.name} from this list`}>Remove</button>
            </li>
          );
        })}
      </ul>
      <p className="muted mt-3 text-xs">Removing a check here only hides it in this browser. <Link href="/history" className="underline">Sign in</Link> to keep reports on every device.</p>
    </section>
  );
}
