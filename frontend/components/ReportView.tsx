import type { AnalysisReport, Finding, RiskLevel, Severity } from "@/lib/types";
import { DownloadReport } from "./DownloadReport";
import { ReportScamButton } from "./ReportScamButton";
import { SCAM_STATUS_LABELS } from "@/lib/scam-status";
import { verificationSummary } from "@/lib/verification";
import { VisaReport } from "./VisaReport";

// Never say "genuine": the best we can honestly report is that no major red flags were found.
type Verdict = { label: string; light: "red" | "amber" | "green" | "off"; accent: string; text: string; ring: string };
const VERDICTS: Record<RiskLevel, Verdict> = {
  HIGH: { label: "Fraud signals found", light: "red", accent: "bg-red-600", text: "text-red-700 dark:text-red-400", ring: "stroke-red-600" },
  MEDIUM: {
    label: "Unverified - check carefully before you act",
    light: "amber",
    accent: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-400",
    ring: "stroke-amber-500",
  },
  LOW: {
    label: "No major red flags found",
    light: "green",
    accent: "bg-emerald-600",
    text: "text-emerald-700 dark:text-emerald-400",
    ring: "stroke-emerald-600",
  },
};
const NOT_CHECKED: Verdict = {
  label: "Not checked - no text could be read",
  light: "off",
  accent: "bg-slate-400",
  text: "text-slate-600 dark:text-slate-400",
  ring: "stroke-slate-400",
};
const MAIN_REASONS = 5;

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  low: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  info: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  const style = SEVERITY_STYLES[level === "HIGH" ? "critical" : level === "MEDIUM" ? "medium" : "info"];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${style}`}>{level}</span>;
}

function TrafficLight({ active }: { active: Verdict["light"] }) {
  const lamp = (colour: "red" | "amber" | "green", on: string) => (
    <span
      className={`block h-5 w-5 rounded-full transition-colors ${active === colour ? on : "bg-slate-600/40 dark:bg-slate-700"}`}
    />
  );
  return (
    <div aria-hidden className="flex w-9 shrink-0 flex-col items-center gap-1.5 rounded-xl bg-slate-900 p-2 shadow-inner dark:bg-black">
      {lamp("red", "bg-red-500 shadow-[0_0_12px_2px_rgba(239,68,68,0.7)]")}
      {lamp("amber", "bg-amber-400 shadow-[0_0_12px_2px_rgba(251,191,36,0.7)]")}
      {lamp("green", "bg-emerald-500 shadow-[0_0_12px_2px_rgba(16,185,129,0.7)]")}
    </div>
  );
}

function ScoreRing({ score, verdict, reviewed = false }: { score: number; verdict: Verdict; reviewed?: boolean }) {
  const circumference = 2 * Math.PI * 42;
  return (
    <div className="relative h-28 w-28 shrink-0">
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden>
        <circle cx="50" cy="50" r="42" className="fill-none stroke-slate-200 dark:stroke-slate-800" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r="42"
          className={`fill-none ${verdict.ring}`}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - score / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-bold tabular-nums ${verdict.text}`}>{score}</span>
        <span className="text-[10px] font-medium text-slate-500 uppercase">{reviewed ? "scan risk / 100" : "risk / 100"}</span>
      </div>
    </div>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const good = finding.points < 0;
  return (
    <li className="flex gap-3 py-3.5">
      <span className={`mt-0.5 h-fit w-[4.5rem] shrink-0 rounded-md px-2 py-0.5 text-center text-[11px] font-semibold uppercase ${SEVERITY_STYLES[good ? "info" : finding.severity]}`}>
        {good ? "good" : finding.severity}
      </span>
      <div className="min-w-0">
        <p className="font-medium text-slate-900 dark:text-slate-100">{finding.title}</p>
        <p className="muted mt-0.5 text-sm leading-relaxed">{finding.detail}</p>
      </div>
    </li>
  );
}

function DetailList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <dt className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="mt-1.5 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span key={item} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs break-all text-slate-800 dark:bg-slate-800 dark:text-slate-200">
            {item}
          </span>
        ))}
      </dd>
    </div>
  );
}

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card p-6 ${className}`}>
      <h2 className="text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

type ReportViewProps = {
  report: AnalysisReport;
  // Saved reports can be reported as scams and downloaded as a PDF.
  saved?: {
    id: string;
    userReported: boolean;
    priceKes: number;
    paymentsReady: boolean;
    unlocked: boolean; // the signed-in user already paid, or is an admin
    token?: string; // unlock token from a paid check, for the PDF download
    checkedAt: string;
  };
};

export function ReportView({ report, saved }: ReportViewProps) {
  const verification = verificationSummary(report);
  const confirmation = report.offer_confirmation;
  const notChecked = !report.text_excerpt.trim();
  const expiredSponsorship = report.findings.some(finding => finding.id === "cos_expired");
  const reviewed = report.scam_status === "CONFIRMED_SCAM" || report.scam_status === "CLEARED";
  const verdict = notChecked ? NOT_CHECKED : report.scam_status === "CONFIRMED_SCAM" ? { ...VERDICTS.HIGH, label: "Confirmed scam — reviewed" }
    : report.scam_status === "CLEARED" ? { ...NOT_CHECKED, label: "Scam report dismissed — reviewed" }
    : report.kind === "visa" && report.risk_level === "HIGH" ? { ...VERDICTS.HIGH, label: "High risk — visa validity or document differences" }
    : report.risk_level === "HIGH" && expiredSponsorship ? { ...VERDICTS.HIGH, label: "High risk — expired sponsorship" } : VERDICTS[report.risk_level];
  // Findings arrive sorted by severity, so the first few are the main reasons.
  const redFlags = report.findings.filter((f) => f.points > 0);
  const mainReasons = redFlags.slice(0, MAIN_REASONS);
  const otherFlags = redFlags.slice(MAIN_REASONS);
  const goodSigns = report.findings.filter((f) => f.points <= 0);
  const e = report.entities;
  const subtitle = [report.job_title, report.country_name, saved && `checked ${saved.checkedAt}`].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <section className="card relative overflow-hidden">
        <div className={`absolute inset-x-0 top-0 h-1.5 ${verdict.accent}`} />
        <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:p-8">
          <div className="flex min-w-0 flex-1 gap-5">
            <TrafficLight active={verdict.light} />
            <div className="min-w-0">
              <p className={`text-sm font-bold tracking-wide uppercase ${verdict.text}`}>{verdict.label}</p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
                {report.company_name ?? (report.kind === "visa" ? "Visa / permit check" : report.kind === "message" ? "Job ad or message" : "Unknown employer")}
              </h1>
              {subtitle && <p className="muted mt-1 text-sm">{subtitle}</p>}
              <p className="mt-4 max-w-2xl leading-relaxed text-slate-800 dark:text-slate-200">{reviewed && <strong>Original scan assessment: </strong>}{report.summary}</p>
            </div>
          </div>
          {!notChecked && <ScoreRing score={report.score} verdict={verdict} reviewed={reviewed} />}
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-8 dark:border-slate-800 dark:bg-slate-900/60">
          <p className="text-xs text-slate-500">
            {report.ai_used ? "Automated checks with an AI assessment" : "Automated document and content checks"} · Review the findings before your next step.
          </p>
          {saved && !notChecked && <ReportScamButton reportId={saved.id} alreadyReported={saved.userReported} scamStatus={report.scam_status} />}
        </div>
      </section>

      {expiredSponsorship && <section role="alert" className="rounded-xl border border-red-300 bg-red-50 p-6 text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">
        <h2 className="font-semibold">Do not use this CoS for a new visa application</h2>
        <p className="mt-2 text-sm">The stated use-by date has passed. Do not pay on the strength of this document as current sponsorship. Request a current record and confirm the sponsor independently.</p>
        <p className="mt-2 text-sm">This validity warning does not prove that the original historical document was forged or that an earlier visa application was invalid.</p>
      </section>}

      {report.visa && <VisaReport visa={report.visa} />}
      <Panel title="Verification completeness">
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><strong>{{ LIMITED: "Limited evidence", PARTIAL: "Partial evidence", COMPLETE: "All listed checks supported" }[verification.level]}</strong>
          <span className="text-sm">{verification.resolved} of {verification.required} checks have conclusive comparisons</span></div>
        <p className="muted mt-2 text-sm">This measures the supporting evidence available. It is separate from scam risk and is not a probability that the offer is genuine. Conflicts still need resolving.</p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">{verification.items.map(item => <div key={item.id} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <dt className="flex flex-wrap justify-between gap-2 text-sm font-semibold"><span>{item.label}</span><span>{{ SUPPORTED: "Supported", CONFLICT: "Conflict", UNVERIFIED: "Unverified", NOT_APPLICABLE: "Not applicable" }[item.status]}</span></dt>
          <dd className="muted mt-2 text-xs leading-relaxed">{item.detail}</dd>
        </div>)}</dl>
      </Panel>

      {report.kind !== "visa" && <Panel title="Employer confirmation">
        <p className="mt-2 font-semibold">{confirmation?.status === "CONFIRMED" && report.scam_status !== "CONFIRMED_SCAM" ? "Employer-confirmed offer — recorded by reviewer" : confirmation?.status === "DENIED" ? "Employer denied this offer — recorded by reviewer" : "Offer not confirmed by the employer"}</p>
        {confirmation && <div className="mt-3 space-y-2 text-sm"><p>{confirmation.note}</p>
          {confirmation.status !== "REVOKED" && <><p>Offer reference: {confirmation.offer_reference} · Role: {confirmation.job_title}</p><p>Employer contact used: {confirmation.employer_contact}</p>
            <p>Employer response: {confirmation.confirmed_at} · Recorded: {confirmation.recorded_at}</p>
            {confirmation.source_url.startsWith("https://") && <a href={confirmation.source_url} target="_blank" rel="noopener noreferrer" className="inline-block underline">Independent contact source ↗</a>}</>}
        </div>}
        <p className="muted mt-2 text-sm">An automated score or matching company record cannot confirm a private offer. A reviewer must record direct employer confirmation of the offer, recruiter and terms. The original scan risk remains visible.</p>
      </Panel>}

      {report.scam_status && <Panel title="Tracked report status">
        <p className="mt-2 font-semibold">{SCAM_STATUS_LABELS[report.scam_status]}</p>
        {report.review_note && <p className="mt-2 text-sm">Reviewer’s reason: {report.review_note}</p>}
        {report.reviewed_at && <p className="muted mt-2 text-xs">Reviewed {report.reviewed_at}</p>}
        <p className="muted mt-2 text-sm">{reviewed ? "The review outcome is tracked separately from the original scan score. Dismissing a scam report does not authenticate the job offer." : "Automated warnings and user reports remain unconfirmed until an administrator reviews the evidence."}</p>
      </Panel>}

      {Boolean(report.memory_matches?.length) && <Panel title="Matches to earlier scam cases">
        <p className="muted mt-2 text-sm">These matches help the checker recognise reused wording and contact or payment details. Previous letters’ private contents are not shown.</p>
        <ul className="mt-4 space-y-4">{report.memory_matches?.map(match => <li key={match.status}>
          <strong className="text-sm">{SCAM_STATUS_LABELS[match.status]}</strong>
          <p className="muted mt-1 text-sm">{match.case_count} distinct pattern(s){match.template_similarity !== null && ` · ${Math.round(match.template_similarity * 100)}% wording similarity`}</p>
          {match.matching_details.length > 0 && <p className="mt-1 text-sm break-all">Matching details: {match.matching_details.map(detail => detail.replace(/^[A-Z]+:/, "")).join(", ")}</p>}
        </li>)}</ul>
      </Panel>}

      {report.warnings.length > 0 && (
        <ul className="space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          {report.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}

      {saved && !notChecked && (
        <DownloadReport
          reportId={saved.id}
          priceKes={saved.priceKes}
          paymentsReady={saved.paymentsReady}
          unlocked={saved.unlocked}
          token={saved.token}
        />
      )}

      {Boolean(report.source_checks?.length) && (
        <Panel title="Company, website and agency evidence">
          <p className="muted mt-2 text-sm">Compare the letter with the sources below. A matching website or business record does not confirm who sent the letter or whether the job exists.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {report.source_checks?.map((check, index) => (
              <div key={`${check.check}:${index}`} className="min-w-0 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">{{ employer: "Employer registration", agency: "Recruitment agency", website: "Website comparison", discovery: "Independent website search", email: "Original recruiter email", sponsorship: "UK sponsorship document", sponsor_registry: "Current Home Office sponsor register", care_provider: "England care-provider registration" }[check.check]}</h3>
                  <span className="text-xs font-semibold">{{ MATCHED: "Details matched", MISMATCH: "Details differ", NOT_FOUND: "Not found in source", UNAVAILABLE: "Check unavailable", UNVERIFIED: "Unverified", NOT_APPLICABLE: "Not applicable" }[check.status]}</span>
                </div>
                <p className="mt-2 text-sm font-medium">{check.subject}</p>
                <p className="muted mt-2 text-sm leading-relaxed">{check.detail}</p>
                {check.record_name && <p className="mt-2 text-xs">Record: {[check.record_name, check.record_id, check.record_status].filter(Boolean).join(" · ")}</p>}
                {Boolean(check.comparisons?.length) && <div className="mt-4 space-y-4">{check.comparisons?.map((comparison) => <div key={comparison.field} className="border-t border-slate-200 pt-3 text-xs dark:border-slate-800">
                  <p className="flex flex-wrap justify-between gap-2 font-semibold"><span>{comparison.field}</span><span className={comparison.status === "MISMATCH" ? "text-amber-700 dark:text-amber-400" : ""}>{{ MATCHED: "Matched", MISMATCH: "Different", UNVERIFIED: "Unverified" }[comparison.status]}</span></p>
                  <p className="mt-2 break-words"><strong>Letter:</strong> {comparison.letter_value}</p>
                  <p className="mt-1 break-words"><strong>Source:</strong> {comparison.source_value}</p>
                  <p className="muted mt-1 leading-relaxed">{comparison.detail}</p>
                </div>)}</div>}
                {Boolean(check.checked_pages?.length) && <details className="mt-3 text-xs"><summary className="cursor-pointer font-medium">Pages checked</summary><ul className="mt-2 space-y-1">{check.checked_pages?.filter(url => url.startsWith("https://")).map(url => <li key={url}><a href={url} target="_blank" rel="noopener noreferrer" className="break-all underline">{url}</a></li>)}</ul></details>}
                {check.source_url.startsWith("https://") && <a href={check.source_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block text-sm font-medium text-blue-700 underline dark:text-blue-400">{check.source_name} ↗</a>}
                <p className="muted mt-2 text-xs">Checked: {check.checked_at}{check.source_updated_at && <> · Snapshot: {check.source_updated_at}</>}</p>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Main reasons" className="lg:col-span-2">
          {mainReasons.length === 0 ? (
            <p className="muted mt-2 text-sm">
              {notChecked ? "Nothing could be checked." : "No red flags were found in the checks we could run."}
            </p>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {mainReasons.map((f) => (
                <FindingRow key={f.id} finding={f} />
              ))}
            </ul>
          )}
          {otherFlags.length > 0 && (
            <details className="group mt-1">
              <summary className="cursor-pointer text-sm font-semibold text-blue-700 dark:text-blue-400">
                Show {otherFlags.length} more red flag{otherFlags.length === 1 ? "" : "s"}
              </summary>
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {otherFlags.map((f) => (
                  <FindingRow key={f.id} finding={f} />
                ))}
              </ul>
            </details>
          )}
          {goodSigns.length > 0 && (
            <>
              <h3 className="mt-6 text-sm font-semibold text-slate-500 uppercase">{report.kind === "visa" ? "Document observations" : "Good signs"}</h3>
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {goodSigns.map((f) => (
                  <FindingRow key={f.id} finding={f} />
                ))}
              </ul>
            </>
          )}
        </Panel>

        <aside className="space-y-6">
          <Panel title="What to do next">
            <ul className="mt-3 space-y-2.5 text-sm">
              {report.advice.map((a) => (
                <li key={a} className="flex gap-2">
                  <span aria-hidden className="mt-0.5 text-blue-700 dark:text-blue-400">
                    ›
                  </span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Verify officially">
            <ul className="mt-3 space-y-2 text-sm">
              {report.verify_links.map((l) => (
                <li key={l.url}>
                  <a href={l.url} target="_blank" rel="noopener noreferrer" className="font-medium text-blue-700 underline-offset-2 hover:underline dark:text-blue-400">
                    {l.label} ↗
                  </a>
                </li>
              ))}
            </ul>
          </Panel>
          {report.checks_not_run.length > 0 && (
            <Panel title="What we could not check">
              <ul className="muted mt-3 list-disc space-y-2 pl-5 text-sm">
                {report.checks_not_run.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </Panel>
          )}
        </aside>
      </div>

      <Panel title="Details found">
        <dl className="mt-4 grid gap-5 sm:grid-cols-2">
          <DetailList label="Emails" items={e.emails} />
          <DetailList label="Phone numbers" items={e.phones} />
          <DetailList label="Websites / domains" items={e.domains} />
          <DetailList label="Amounts of money" items={e.money} />
          <DetailList label="Payment details (M-Pesa, bank, crypto)" items={e.payment_accounts ?? []} />
          <DetailList
            label="Recruitment agency"
            items={[e.agency_name, e.agency_licence && `Licence ${e.agency_licence}`].filter((v): v is string => Boolean(v))}
          />
        </dl>
        {report.text_excerpt && (
          <details className="mt-5">
            <summary className="cursor-pointer text-sm font-semibold text-blue-700 dark:text-blue-400">Show the text that was read</summary>
            <pre className="mt-3 max-h-80 overflow-auto rounded-xl bg-slate-100 p-4 text-xs whitespace-pre-wrap dark:bg-slate-950">
              {report.text_excerpt}
            </pre>
          </details>
        )}
      </Panel>

      <p className="text-center text-xs text-slate-500">
        This is an automated risk assessment, not a legal verdict. A low score does not guarantee an offer is real - always
        confirm directly with the employer through contact details you find yourself.
      </p>
    </div>
  );
}
