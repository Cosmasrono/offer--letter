"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { SCAM_STATUS_LABELS } from "@/lib/scam-status";
import type { ScamStatus } from "@/lib/types";

export type ReviewCase = { id: string; fileName: string; scamStatus: ScamStatus; createdAt: string; reviewNote: string | null };
type ReviewEvent = { action: string; from: ScamStatus; to: ScamStatus; at: string; note: string; sourceUrl: string | null };

export function ScamReviewQueue({ reports }: { reports: ReviewCase[] }) {
  const router = useRouter();
  const [selected, setSelected] = useState("");
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Record<string, ReviewEvent[]>>({});
  async function loadHistory(id: string) {
    try {
      const response = await fetch(`/api/scam-review?id=${id}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setHistory(current => ({ ...current, [id]: data.history }));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "History could not be loaded."); }
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true; setSaving(true); setError(""); setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/scam-review", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: selected, action: form.get("action"), note: form.get("note"), sourceUrl: form.get("sourceUrl") }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "The decision could not be saved.");
      setMessage(`Saved: ${SCAM_STATUS_LABELS[data.scamStatus as ScamStatus]}. Future scans will use the updated decision.`);
      setSelected(""); setHistory({}); router.refresh();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "The decision could not be saved."); }
    finally { setSaving(false); submitting.current = false; }
  }
  return <div className="space-y-4">
    <p className="muted text-sm">Verify the case before confirming it. Dismissed cases stop contributing to future scam matches. Existing automated scores are retained as a record of the original check.</p>
    {error && <p role="alert" className="alert-error">{error}</p>}
    {message && <p role="status" className="card p-4 text-sm">{message}</p>}
    {!reports.length && <p className="card p-6">No cases in this queue.</p>}
    {reports.map(report => <section key={report.id} className="card space-y-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold break-all">{report.fileName}</h2><p className="muted mt-1 text-xs">{new Date(report.createdAt).toLocaleString()} · {report.id}</p></div><span className="text-sm font-semibold">{SCAM_STATUS_LABELS[report.scamStatus]}</span></div>
      {report.reviewNote && <p className="text-sm">Latest review: {report.reviewNote}</p>}
      <div className="flex flex-wrap gap-3"><Link href={`/report/${report.id}`} className="text-sm underline">Open report</Link><button type="button" disabled={saving} className="text-sm underline" onClick={() => setSelected(report.id)}>Review status</button><button type="button" className="text-sm underline" onClick={() => void loadHistory(report.id)}>Decision history</button></div>
      {history[report.id] && <ol className="space-y-2 border-t pt-3 text-sm">{history[report.id].length ? history[report.id].map((entry, index) => <li key={index}><strong>{SCAM_STATUS_LABELS[entry.from]} → {SCAM_STATUS_LABELS[entry.to]}</strong><p>{entry.note}</p><p className="muted text-xs">{new Date(entry.at).toLocaleString()}</p>{entry.sourceUrl?.startsWith("https://") && <a href={entry.sourceUrl} target="_blank" rel="noopener noreferrer" className="underline">Review source ↗</a>}</li>) : <li>No manual decisions yet.</li>}</ol>}
      {selected === report.id && <form onSubmit={submit} className="space-y-3 border-t pt-4">
        <div><label htmlFor={`action-${report.id}`} className="label">Decision</label><select id={`action-${report.id}`} name="action" className="field" disabled={saving}><option value="CONFIRM_SCAM">Confirm scam</option><option value="CLEAR">Dismiss scam report</option><option value="REOPEN">Reopen for investigation</option></select></div>
        <div><label htmlFor={`note-${report.id}`} className="label">Evidence and reason</label><textarea id={`note-${report.id}`} name="note" required minLength={20} maxLength={2000} rows={4} className="field h-auto py-3" disabled={saving} placeholder="Explain how you verified the case and what evidence supports your decision." /></div>
        <div><label htmlFor={`source-${report.id}`} className="label">Evidence source link (optional)</label><input id={`source-${report.id}`} name="sourceUrl" type="url" className="field" disabled={saving} placeholder="https://…" /></div>
        <button type="submit" disabled={saving} className="btn-primary">{saving ? "Saving…" : "Save decision"}</button>
      </form>}
    </section>)}
  </div>;
}
