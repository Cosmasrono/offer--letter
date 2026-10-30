"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function OfferConfirmationForm({ reportId, token = "" }: { reportId: string; token?: string }) {
  const router = useRouter();
  const [status, setStatus] = useState("CONFIRMED");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = { ...Object.fromEntries(form), id: reportId, token, status,
      independentContact: form.has("independentContact"), recruiterConfirmed: form.has("recruiterConfirmed"), termsConfirmed: form.has("termsConfirmed") };
    try {
      if (body.confirmed_at) body.confirmed_at = new Date(String(body.confirmed_at)).toISOString();
      const response = await fetch("/api/offer-confirmation", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Could not save employer confirmation.");
      router.refresh();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not save employer confirmation."); }
    finally { setBusy(false); }
  }
  return <details className="card p-6">
    <summary className="cursor-pointer font-semibold">Record employer confirmation (reviewer)</summary>
    <p className="muted mt-3 text-sm">Record a response already obtained through independently sourced employer contacts. This form does not contact anyone. The original scan risk stays visible.</p>
    <form onSubmit={save} className="mt-4 space-y-4">
      <label className="block"><span className="label">Employer response</span><select className="field" value={status} onChange={event => setStatus(event.target.value)} disabled={busy}>
        <option value="CONFIRMED">Confirmed the offer and recruiter</option><option value="DENIED">Denied this offer</option><option value="REVOKED">Withdraw an earlier confirmation</option>
      </select></label>
      {status !== "REVOKED" && <>
        <div className="grid gap-4 sm:grid-cols-2">{[["employer_contact", "Employer contact used"], ["offer_reference", "Offer reference"], ["job_title", "Job title"]].map(([name, label]) => <label key={name} className="block"><span className="label">{label}</span><input name={name} required maxLength={name === "employer_contact" ? 250 : 150} className="field" disabled={busy} /></label>)}
          <label className="block"><span className="label">When the employer responded</span><input name="confirmed_at" type="datetime-local" required className="field" disabled={busy} /></label>
        </div>
        <label className="block"><span className="label">Independent source for employer contact</span><input name="source_url" type="url" required placeholder="https://company.com/contact" maxLength={1000} className="field" disabled={busy} /></label>
        <label className="flex items-start gap-2 text-sm"><input name="independentContact" type="checkbox" required disabled={busy} />I verified the employer contact independently of the letter and recruiter.</label>
        {status === "CONFIRMED" && <><label className="flex items-start gap-2 text-sm"><input name="recruiterConfirmed" type="checkbox" required disabled={busy} />The employer confirmed this recruiter is authorized.</label>
          <label className="flex items-start gap-2 text-sm"><input name="termsConfirmed" type="checkbox" required disabled={busy} />The employer confirmed the offer reference, role and terms.</label></>}
      </>}
      <label className="block"><span className="label">Evidence and employer response</span><textarea name="note" required minLength={30} maxLength={2000} rows={4} className="field h-auto py-3" placeholder="Record what HR confirmed or denied and the confirmation reference. This note is included in the report." disabled={busy} /></label>
      {error && <p role="alert" className="alert-error">{error}</p>}
      <button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save employer response"}</button>
    </form>
  </details>;
}
