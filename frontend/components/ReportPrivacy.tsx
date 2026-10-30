"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function ReportPrivacy({ id, expiresAt, canDelete }: { id: string; expiresAt: string | null; canDelete: boolean }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/report-privacy", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
      if (!response.ok) throw new Error((await response.json()).error || "The report could not be deleted. Try again.");
      try { localStorage.removeItem(`olc-report-download-${id}`); localStorage.removeItem(`olc-report-payment-${id}`); } catch { /* Optional browser storage. */ }
      router.replace("/report-deleted"); router.refresh();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "The report could not be deleted. Try again."); setBusy(false); }
  }
  return <section className="card space-y-3 p-5 text-sm" aria-label="Your report privacy">
    <h2 className="font-semibold">Your report, your choice</h2>
    <p className="muted">{expiresAt ? `Available until ${new Date(expiresAt).toLocaleString("en-GB", { timeZone: "Africa/Nairobi", dateStyle: "medium", timeStyle: "short" })} (Nairobi time), then automatically removed.` : "This report was created before the current retention notice."} <Link href="/privacy" className="underline">Privacy notice</Link></p>
    {canDelete ? confirming ? <div className="space-y-3"><p>Delete this report and stop using its details for future pattern searches? This also removes access to any paid findings and PDFs. Payment records and copies already downloaded are kept separately.</p><div className="flex flex-wrap gap-3"><button type="button" onClick={remove} disabled={busy} className="btn-primary">{busy ? "Deleting…" : "Yes, delete permanently"}</button><button type="button" onClick={() => setConfirming(false)} disabled={busy} className="btn-secondary">Keep report</button></div></div> : <button type="button" onClick={() => setConfirming(true)} className="underline">Delete this report</button> : <p className="muted text-xs">To delete, sign in as the owner or use the browser that submitted this guest report. For help, contact the service operator.</p>}
    {error && <p role="alert" className="alert-error">{error}</p>}
  </section>;
}
