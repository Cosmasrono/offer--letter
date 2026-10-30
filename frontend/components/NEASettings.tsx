"use client";

import { useEffect, useState } from "react";

type Dataset = { records: number; fresh: boolean; retrieved_at: string | null; source_url: string };

export function NEASettings() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/verification/nea", { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error ?? "Could not load registry status.");
        setDataset(data);
      }).catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Could not load registry status."); });
    return () => controller.abort();
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true); setError(""); setMessage("");
    try {
      const body = new FormData(event.currentTarget);
      const date = new Date(String(body.get("retrieved_at")));
      if (!Number.isFinite(date.getTime())) throw new Error("Enter when you retrieved the export.");
      body.set("retrieved_at", date.toISOString());
      const response = await fetch("/api/verification/nea", { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "The export could not be imported.");
      setDataset(data);
      setMessage(`${data.records} agency records imported. This snapshot is available when the live register cannot be read.`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The export could not be imported.");
    } finally { setSaving(false); }
  }

  return <div className="card space-y-5 p-6">
    <div><h2 className="text-lg font-semibold">NEA agency register</h2><p className="muted mt-2 text-sm">New scans try the live NEA register for named agencies. Import a dated copy as a fallback when the live source is unavailable. Include agency email and website columns to help detect impersonation.</p></div>
    {dataset && <p className="rounded-xl bg-slate-100 p-4 text-sm dark:bg-slate-900"><strong>{dataset.records} records · {dataset.fresh ? "Current snapshot" : "Refresh required"}</strong><br />{dataset.retrieved_at ? `Retrieved ${new Date(dataset.retrieved_at).toLocaleString()}` : "No dated snapshot imported."}</p>}
    <p className="text-sm"><a href="https://neaims.go.ke/home/agencies-info" target="_blank" rel="noopener noreferrer" className="font-medium text-blue-700 underline dark:text-blue-400">Open the official NEA register ↗</a><br /><span className="muted">Use an official CSV or HTML table export with agency name, recruitment licence number, certificate expiry and status. A business registration number is separate from the recruitment licence. Refresh within 30 days.</span></p>
    <form onSubmit={submit} className="space-y-4">
      <div><label htmlFor="nea-export" className="label">Official HTML or CSV export</label><input id="nea-export" name="file" type="file" accept=".html,.htm,.csv" required disabled={saving} className="field h-auto py-3" /></div>
      <div><label htmlFor="nea-retrieved" className="label">When you retrieved this export</label><input id="nea-retrieved" name="retrieved_at" type="datetime-local" required disabled={saving} className="field" /></div>
      <button type="submit" disabled={saving} className="btn-primary">{saving ? "Importing…" : "Import agency register"}</button>
    </form>
    {error && <p role="alert" className="alert-error">{error}</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
    <p className="muted text-xs">A matching licence does not authenticate the sender or the job offer. An agency absent from a snapshot is referred for a live check.</p>
  </div>;
}
