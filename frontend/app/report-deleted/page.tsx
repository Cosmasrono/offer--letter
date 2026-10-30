import Link from "next/link";

export default function ReportDeletedPage() {
  return <div className="card mx-auto max-w-lg space-y-4 p-8"><h1 className="text-2xl font-semibold">Your report has been deleted</h1><p>Its saved contents and matching patterns have been removed. The report link and PDF download no longer work.</p><p className="muted text-sm">Payment records and copies already downloaded are separate.</p><Link href="/#check" className="btn-primary">Check another offer</Link></div>;
}
