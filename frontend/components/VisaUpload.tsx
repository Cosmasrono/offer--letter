"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ConsentNotice } from "./ConsentNotice";
import { CONSENT_VERSION } from "@/lib/privacy-policy";
import type { VisaDetails, VisaPreview } from "@/lib/types";

export const VISA_FIELD_LABELS: Record<keyof VisaDetails, string> = {
  holder_name: "Holder name", passport_number: "Passport number", visa_number: "Visa / permit number", nationality: "Nationality",
  sponsor: "Employer / sponsor", job_title: "Job title", visa_type: "Visa type", issue_date: "Visa issue date", expiry_date: "Visa / entry expiry date",
};

export function VisaUpload({ priceKes }: { priceKes: number }) {
  const router = useRouter();
  const submitting = useRef(false);
  const [consent, setConsent] = useState<{ memory: boolean } | null>(null);
  const [country, setCountry] = useState("QA");
  const [file, setFile] = useState<File | null>(null);
  const [offer, setOffer] = useState<File | null>(null);
  const [preview, setPreview] = useState<VisaPreview | null>(null);
  const [details, setDetails] = useState<VisaDetails | null>(null);
  const [offerDetails, setOfferDetails] = useState<VisaDetails | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState<"preview" | "scan" | null>(null);
  const [error, setError] = useState("");

  function body() {
    const form = new FormData();
    form.set("consentVersion", CONSENT_VERSION); form.set("processingConsent", "true"); form.set("submissionAuthority", "true");
    form.set("memoryConsent", "false"); // Government document templates and passport fields never enter scam memory.
    form.set("kind", "visa"); form.set("country", country);
    if (file) form.set("file", file);
    if (offer) form.set("offerFile", offer);
    return form;
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!consent || !file || submitting.current || preview && !reviewed) return;
    submitting.current = true; setBusy(preview ? "scan" : "preview"); setError("");
    const form = body();
    if (preview) form.set("visaReview", JSON.stringify({ reviewed: true, details, offer_details: offerDetails }));
    try {
      const response = await fetch(preview ? "/api/analyze" : "/api/visa-preview", { method: "POST", body: form, headers: { "X-Consent-Version": CONSENT_VERSION } });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Your documents could not be checked. Try again.");
      if (preview) {
        if (!result.id) throw new Error("The report could not be saved. You have not been charged.");
        router.push(`/report/${result.id}`);
      } else {
        const extracted = result as VisaPreview;
        setPreview(extracted); setDetails(extracted.details); setOfferDetails(extracted.offer_details); setReviewed(false);
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : "The service is unavailable. Try again."); }
    finally { submitting.current = false; setBusy(null); }
  }
  function reset() { setPreview(null); setDetails(null); setOfferDetails(null); setReviewed(false); setError(""); }
  function chooseFile(value: File | null, isOffer = false) {
    reset();
    if (value && (value.size === 0 || value.size > 10 * 1024 * 1024)) { setError("Choose a non-empty document smaller than 10 MB."); return; }
    if (isOffer) setOffer(value); else setFile(value);
  }
  return <div className="upload-card">
    <div className="upload-heading"><div><h2>Check the details before you travel.</h2><p>Qatar and Kuwait · visa or entry/work permit</p></div><div className="upload-price"><strong>{priceKes ? `KES ${priceKes}` : "Free testing"}</strong><span>report + PDF</span></div></div>
    {!consent ? <ConsentNotice mode="visa" onAccept={memory => setConsent({ memory })} /> : <form onSubmit={submit} className="space-y-5 p-5 sm:p-7">
      <ol className="muted flex flex-wrap gap-4 text-xs" aria-label="Visa check progress"><li>1. Documents</li><li aria-current={preview ? "step" : undefined}>2. Review details</li><li>3. Check and reveal</li></ol>
      <p className="muted text-xs">Visa documents and passport details are excluded from shared scam patterns. <button type="button" className="underline" disabled={Boolean(busy)} onClick={() => { reset(); setFile(null); setOffer(null); setConsent(null); }}>Review consent</button></p>
      {busy ? <div role="status" className="card space-y-3 p-6"><p className="font-semibold">{busy === "preview" ? "Reading the visa and offer details…" : "Checking validity and comparing your documents…"}</p><p className="muted text-sm">Keep this page open. Scanned documents may take a few minutes.</p></div> : preview && details ? <>
        <div><h3 className="text-lg font-semibold">Review the extracted details</h3><p className="muted mt-2 text-sm">Compare these values with the original documents. Correct reading mistakes and leave unavailable fields empty. Use YYYY-MM-DD only when you can confirm the date. Your changes will be recorded separately from the original extraction.</p></div>
        {preview.warnings.map((warning, index) => <p key={index} className="muted text-xs">{warning}</p>)}
        <ReviewFields title="Visa details" prefix="visa" details={details} original={preview.details} onChange={setDetails} />
        {offerDetails && preview.offer_details && <ReviewFields title="Offer details for comparison" prefix="offer" details={offerDetails} original={preview.offer_details} onChange={setOfferDetails} offer />}
        <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>I checked these values against the original documents. I understand that corrections and matching details do not confirm authenticity.</span></label>
        <button type="submit" disabled={!reviewed} className="btn-primary w-full">Check visa{offer ? " and compare offer" : ""}</button>
        <button type="button" onClick={reset} className="btn-secondary w-full">Change documents or country</button>
      </> : <>
        <label className="block"><span className="label">Issuing country</span><select className="field" value={country} onChange={event => setCountry(event.target.value)}><option value="QA">Qatar</option><option value="KW">Kuwait</option></select></label>
        <label className="block"><span className="label">Visa or permit document</span><input className="field h-auto py-3" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt" onChange={event => chooseFile(event.target.files?.[0] ?? null)} />{file && <span className="muted mt-2 block break-all text-xs">Selected: {file.name}</span>}</label>
        <label className="block"><span className="label">Offer letter to compare <span className="muted">(optional)</span></span><input className="field h-auto py-3" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.eml" onChange={event => chooseFile(event.target.files?.[0] ?? null, true)} />{offer && <span className="muted mt-2 block break-all text-xs">Selected: {offer.name}</span>}</label>
        {offer && <button type="button" className="text-sm underline" onClick={() => setOffer(null)}>Remove optional offer</button>}
        <p className="muted text-xs">Up to 10 MB per document. We compare labelled names, passport numbers, employers/sponsors and job titles. Salary is not compared because a visa may not state it. For full employer and agency checks, <Link href="/#check" className="underline">check the offer letter separately</Link>.</p>
        <button type="submit" disabled={!file} className="btn-primary w-full">Read documents for review</button>
      </>}
      {error && <p role="alert" className="alert-error">{error}</p>}
      <p className="muted text-xs">{priceKes ? `Payment is requested only after the checked report is saved. KES ${priceKes} unlocks findings and the PDF.` : "Free local testing is enabled."} Official government status remains unverified; opening an official link does not change it.</p>
    </form>}
  </div>;
}

function ReviewFields({ title, prefix, details, original, onChange, offer = false }: { title: string; prefix: string; details: VisaDetails; original: VisaDetails; onChange: (details: VisaDetails) => void; offer?: boolean }) {
  const keys = (Object.keys(VISA_FIELD_LABELS) as (keyof VisaDetails)[]).filter(key => !offer || ["holder_name", "passport_number", "nationality", "sponsor", "job_title"].includes(key));
  return <fieldset className="space-y-4 rounded-xl border p-4"><legend className="px-2 font-semibold">{title}</legend><div className="grid gap-4 sm:grid-cols-2">{keys.map(key => <label key={key} htmlFor={`${prefix}-${key}`} className="block min-w-0"><span className="label">{VISA_FIELD_LABELS[key]}</span><input id={`${prefix}-${key}`} className="field" value={details[key] || ""} maxLength={key.endsWith("number") ? 50 : key.endsWith("date") ? 60 : ["nationality", "visa_type"].includes(key) ? 100 : 200} onChange={event => onChange({ ...details, [key]: event.target.value || null })} placeholder={key.endsWith("date") ? "YYYY-MM-DD, if clearly stated" : "Not found — leave empty if unavailable"} /><span className="muted mt-1 block break-words text-xs">Read as: {original[key] || "not found"}</span></label>)}</div></fieldset>;
}
