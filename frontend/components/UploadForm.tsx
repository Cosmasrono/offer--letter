"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { COUNTRIES } from "@/lib/countries";
import type { AnalyzeResponse, Kind } from "@/lib/types";
import { Icon } from "./Icon";
import { ConsentNotice } from "./ConsentNotice";
import { CONSENT_VERSION } from "@/lib/privacy-policy";
import { rememberReport } from "@/lib/recent-reports";
import Link from "next/link";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.txt,.eml";
const ACCEPT_SCREENSHOT = ".png,.jpg,.jpeg,.webp";

const TABS: { kind: Kind; label: string }[] = [
  { kind: "letter", label: "Offer letter" },
  { kind: "message", label: "Job ad or message" },
];

// What the check looks at, shown one by one while it runs (it takes up to a minute).
const CHECK_STAGES = [
  "Reading your document",
  "Looking for fee and payment requests",
  "Checking emails, phone numbers and websites",
  "Comparing the letter with public website details",
  "Checking the recruitment agency with NEA",
  "Applying the destination country's hiring rules",
  "Comparing with scams reported before",
  "Writing your report",
];

type Credit = { paymentId: string; token: string };
type Props = { priceKes: number };

export function UploadForm({ priceKes }: Props) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<Kind>("letter");
  const [consent, setConsent] = useState<{ memory: boolean } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [messageText, setMessageText] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [country, setCountry] = useState("");
  const [dragging, setDragging] = useState(false);
  const [credit, setCredit] = useState<Credit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const scanning = useRef(false);
  const ready = kind === "letter" ? Boolean(file) : Boolean(messageText.trim() || screenshot);

  // Honour existing paid credits after the change to scanning first.
  useEffect(() => {
    if (priceKes === 0) return;
    let active = true;
    try {
      const saved = JSON.parse(localStorage.getItem("olc-check-credit") ?? "null");
      if (saved?.paymentId && saved?.token) {
        fetch(`/api/payments?id=${saved.paymentId}`, { cache: "no-store" })
          .then((res) => res.ok ? res.json() : null)
          .then((state) => { if (active && state?.status === "SUCCESS" && state.available) setCredit(saved); })
          .catch(() => {});
      }
    } catch { /* Browser storage is optional. */ }
    return () => { active = false; };
  }, [priceKes]);

  useEffect(() => {
    if (startedAt === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  function chooseFile(nextFile: File | null, screenshotOnly = false) {
    if (!nextFile) return;
    const extension = nextFile.name.split(".").pop()?.toLowerCase();
    const allowed = screenshotOnly ? ["png", "jpg", "jpeg", "webp"] : ["pdf", "png", "jpg", "jpeg", "webp", "txt", "eml"];
    if (!extension || !allowed.includes(extension)) {
      setError(screenshotOnly ? "Not checked — file type not recognized. Choose a JPG, PNG or WEBP screenshot." : "Not checked — file type not recognized. Choose a PDF, JPG, PNG, WEBP, TXT or original EML email.");
      return;
    }
    if (nextFile.size === 0 || nextFile.size > 10 * 1024 * 1024) {
      setError(nextFile.size === 0 ? "This file is empty. Choose another file." : "This file is too large. Choose a file under 10 MB.");
      return;
    }
    setError(null);
    if (screenshotOnly) setScreenshot(nextFile);
    else setFile(nextFile);
  }


  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready || !consent || scanning.current) return;
    scanning.current = true;
    setError(null);
    setStartedAt(Date.now());
    setNow(Date.now());
    const body = new FormData();
    body.append("consentVersion", CONSENT_VERSION);
    body.append("processingConsent", "true");
    body.append("submissionAuthority", "true");
    body.append("memoryConsent", String(consent.memory));
    body.append("kind", kind);
    if (kind === "letter" && file) body.append("file", file);
    else if (screenshot) body.append("file", screenshot);
    else body.append("text", messageText);
    if (country) body.append("country", country);
    if (credit && priceKes > 0) { body.append("paymentId", credit.paymentId); body.append("paymentToken", credit.token); }
    try {
      const response = await fetch("/api/analyze", { method: "POST", body, headers: { "X-Consent-Version": CONSENT_VERSION } });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "The scan could not be completed. Please try again.");
      const { id, token, report } = data as AnalyzeResponse;
      if (!id) throw new Error("Your scan could not be saved. Please try again.");
      const pasted = messageText.trim().replace(/\s+/g, " ");
      rememberReport({
        id, kind, checkedAt: new Date().toISOString(), risk: report?.risk_level,
        name: (kind === "letter" ? file?.name : screenshot?.name) ?? (pasted.length > 40 ? `${pasted.slice(0, 40)}…` : pasted || "Pasted message"),
      });
      if (token) {
        try {
          localStorage.setItem(`olc-report-download-${id}`, token);
          localStorage.removeItem("olc-check-credit");
        } catch { /* The token in the URL still opens the report. */ }
      }
      router.push(`/report/${id}${token ? `?token=${encodeURIComponent(token)}` : ""}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The connection dropped. Please try again. You have not been charged.");
      setStartedAt(null);
      scanning.current = false;
    }
  }

  return (
    <div className="upload-card">
      <div className="upload-heading">
        <div><h2>Let&apos;s check your offer.</h2><p>{priceKes === 0 ? "Free testing. Read your findings after scanning." : "Scan first. Unlock the findings when you’re ready."}</p></div>
        <div className="upload-price"><strong>{priceKes === 0 ? "Free testing" : `KES ${priceKes}`}</strong><span>{priceKes === 0 ? "report + PDF included" : "to unlock · PDF included"}</span></div>
      </div>
      <ol className="upload-stepper flex items-center gap-3 border-b font-medium" aria-label="Check progress">
        {["Consent", "Upload", "Scan", priceKes === 0 ? "Report" : "Reveal"].map((label, i) => <li key={label} aria-current={i === (!consent ? 0 : startedAt === null ? 1 : 2) ? "step" : undefined} className="flex flex-1 items-center gap-2"><span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${i === (!consent ? 0 : startedAt === null ? 1 : 2) ? "bg-blue-700 text-white" : "bg-slate-200 text-slate-500 dark:bg-slate-800"}`}>{i + 1}</span><span>{label}</span></li>)}
      </ol>
      {!consent ? <ConsentNotice onAccept={memory => setConsent({ memory })} /> : startedAt !== null ? <CheckingProgress seconds={Math.max(0, Math.floor((now - startedAt) / 1000))} /> : (
          <form onSubmit={onSubmit} className="upload-form space-y-5">
            <div className="flex items-center justify-between gap-3 text-xs"><span className="muted">Consent given · pattern sharing {consent.memory ? "on" : "off"}</span><button type="button" className="underline" onClick={() => { setConsent(null); setFile(null); setScreenshot(null); setMessageText(""); setError(null); }}>Review choices</button></div>
            <div role="group" aria-label="What do you want to check?" className="upload-tabs">
              {TABS.map((t) => (
                <button
                  key={t.kind}
                  type="button"
                  aria-pressed={kind === t.kind}
                  onClick={() => {
                    setKind(t.kind);
                    setError(null);
                  }}
                  className="upload-tab"
                >
                  <Icon name={t.kind === "letter" ? "file" : "message"} className="h-4 w-4 shrink-0" />
                  <span>{t.label}</span>
                </button>
              ))}
            </div>

            <p className="muted text-sm">Have a Qatar or Kuwait visa? <Link href="/visa" className="font-medium underline">Check a visa or compare it with your offer</Link>.</p>
            {kind === "letter" ? (
              <div
                role="button"
                aria-label={file ? `Change selected file: ${file.name}` : "Upload an offer letter"}
                tabIndex={0}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    inputRef.current?.click();
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  chooseFile(e.dataTransfer.files[0] ?? null);
                }}
                className={`upload-dropzone ${dragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
              >
                {file ? (
                  <>
                    <span aria-hidden className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-emerald-600 text-white">
                      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 5 5L20 7" /></svg>
                    </span>
                    <p className="font-semibold break-all">{file.name}</p>
                    <p className="text-sm text-slate-500">{(file.size / 1024).toFixed(0)} KB · click to choose a different file</p>
                  </>
                ) : (
                  <>
                    <span className="upload-symbol"><Icon name="upload" className="h-6 w-6" /></span>
                    <strong>Drop your offer letter here</strong>
                    <strong className="mt-1">or <span>browse your files</span></strong>
                    <p>PDF, JPG, PNG, WEBP, TXT or EML · up to 10 MB</p>
                  </>
                )}
                <input ref={inputRef} type="file" accept={ACCEPT} aria-label="Choose an offer letter file" className="hidden" onChange={(e) => { chooseFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
              </div>
            ) : (
              <div className="space-y-2">
                <label htmlFor="message-text" className="label">Paste the job ad, WhatsApp, Facebook or SMS message</label>
                <textarea
                  id="message-text"
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  disabled={Boolean(screenshot)}
                  rows={7}
                  maxLength={20000}
                  placeholder={"e.g. DUBAI JOBS - Cleaners and drivers needed. Salary 120,000/=. Registration fee 3,500 only. Send to M-Pesa Till…"}
                  className="field h-auto py-3 leading-relaxed disabled:opacity-50"
                />
                <div className="muted flex flex-wrap items-center gap-2 text-sm">
                  {screenshot ? (
                    <>
                      <span className="break-all">Screenshot: {screenshot.name}</span>
                      <button type="button" onClick={() => setScreenshot(null)} className="underline">remove</button>
                    </>
                  ) : (
                    <label className="cursor-pointer font-medium text-blue-700 hover:underline dark:text-blue-400">
                      Or attach a screenshot instead
                      <input type="file" accept={ACCEPT_SCREENSHOT} className="sr-only" onChange={(e) => { chooseFile(e.target.files?.[0] ?? null, true); e.target.value = ""; }} />
                    </label>
                  )}
                </div>
              </div>
            )}

            {kind === "letter" && <p className="muted text-xs">You can also export the original recruiter email as .eml to check its sender, reply address and PDF attachments. Save the original message rather than forwarding it.</p>}
            <label className="block">
              <span className="label">Where is the opportunity? <span className="muted font-normal">(optional)</span></span>
              <span className="country-field block">
              <Icon name="globe" />
              <select value={country} onChange={(e) => setCountry(e.target.value)} className="field" aria-label="Country of the job">
                <option value="">Detect automatically</option>
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
              </span>
            </label>

            {credit && priceKes > 0 && (
              <p className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">
                <Tick /> You have a paid check ready to use - no need to pay again.
              </p>
            )}
            {error && <p role="alert" className="alert-error">{error}</p>}

            <button type="submit" disabled={!ready} className="btn-primary checker-submit w-full">
              {kind === "letter" ? "Scan my letter" : "Scan this message"}
              <Icon name="arrow" className="h-4 w-4" />
            </button>
            <p className="upload-privacy">
              <Icon name="lock" className="h-3 w-3" />
              {priceKes === 0 ? "No payment needed during testing. Findings and PDF are included." : `Scan first. Pay KES ${priceKes} to reveal findings and download the PDF.`}
            </p>
          </form>
      )}
    </div>
  );
}

function CheckingProgress({ seconds }: { seconds: number }) {
  // Advance a stage every ~6s, holding on the last one until the result arrives.
  const current = Math.min(CHECK_STAGES.length - 1, Math.floor(seconds / 6));
  return (
    <div role="status" aria-live="polite" className="p-6 sm:p-8">
      <div className="flex items-center gap-3">
        <span aria-hidden className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        <p className="text-lg font-semibold">Checking your document…</p>
        <span className="ml-auto text-sm text-slate-500 tabular-nums">{seconds}s</span>
      </div>
      <ul className="mt-6 space-y-3">
        {CHECK_STAGES.map((stage, i) => (
          <li key={stage} className={`flex items-center gap-3 text-sm transition-opacity ${i > current ? "opacity-40" : ""}`}>
            {i < current ? (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-[10px] text-white">✓</span>
            ) : i === current ? (
              <span className="h-5 w-5 animate-pulse rounded-full bg-blue-600/80" />
            ) : (
              <span className="h-5 w-5 rounded-full border-2 border-slate-300 dark:border-slate-700" />
            )}
            <span className={i === current ? "font-medium" : ""}>{stage}</span>
          </li>
        ))}
      </ul>
      <p className="muted mt-6 text-xs">This usually takes under a minute. Keep this page open.</p>
    </div>
  );
}

function Tick() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-emerald-600" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="m5 12 5 5L20 7" />
    </svg>
  );
}

